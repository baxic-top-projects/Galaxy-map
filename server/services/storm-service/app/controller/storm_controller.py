from __future__ import annotations

from fastapi import APIRouter, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.responses import JSONResponse

from app.dto.storm import SystemStormResponseDto
from app.service.storm_broadcast_service import storm_broadcast
from app.service.storm_simulation_service import StormSimulationService

router = APIRouter()


def get_simulator() -> StormSimulationService:
    from app.main import simulator

    if simulator is None:
        raise HTTPException(status_code=503, detail="Simulator not ready")
    return simulator


@router.get("/internal/v1/storms")
def get_storms():
    return JSONResponse(get_simulator().public_snapshot())


@router.get("/internal/v1/storms/systems/{system_id:path}", response_model=SystemStormResponseDto)
def get_system_storm(system_id: str) -> SystemStormResponseDto:
    sim = get_simulator()
    if system_id not in sim.graph.systems:
        raise HTTPException(status_code=404, detail="Unknown system")
    state = sim.system_state(system_id)
    return SystemStormResponseDto(
        systemId=system_id,
        active=state is not None,
        storm=state,
    )


@router.post("/internal/v1/storms/tick")
async def force_tick():
    from app.main import _schedule_kafka_publish

    sim = get_simulator()
    await __import__("asyncio").to_thread(sim.step)
    payload = sim.public_snapshot()
    await storm_broadcast.broadcast_json(payload)
    _schedule_kafka_publish(payload)
    return JSONResponse(payload)


@router.websocket("/internal/v1/storms/ws")
async def storms_ws(websocket: WebSocket) -> None:
    await storm_broadcast.connect(websocket)
    try:
        await websocket.send_json(get_simulator().public_snapshot())
        while True:
            # Keep the socket alive; clients are receive-only for now.
            await websocket.receive_text()
    except WebSocketDisconnect:
        pass
    finally:
        await storm_broadcast.disconnect(websocket)
