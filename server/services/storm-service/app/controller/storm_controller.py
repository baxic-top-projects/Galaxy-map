from __future__ import annotations

from fastapi import APIRouter, HTTPException, WebSocket, WebSocketDisconnect

from app.dto.storm import StormSnapshotDto, SystemStormResponseDto
from app.service.storm_broadcast_service import storm_broadcast
from app.service.storm_simulation_service import StormSimulationService

router = APIRouter()


def get_simulator() -> StormSimulationService:
    from app.main import simulator

    if simulator is None:
        raise HTTPException(status_code=503, detail="Simulator not ready")
    return simulator


@router.get("/internal/v1/storms", response_model=StormSnapshotDto)
def get_storms() -> StormSnapshotDto:
    return get_simulator().snapshot()


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


@router.post("/internal/v1/storms/tick", response_model=StormSnapshotDto)
async def force_tick() -> StormSnapshotDto:
    sim = get_simulator()
    snapshot = await __import__("asyncio").to_thread(sim.step)
    await storm_broadcast.broadcast_json(snapshot.model_dump(mode="json"))
    return snapshot


@router.websocket("/internal/v1/storms/ws")
async def storms_ws(websocket: WebSocket) -> None:
    await storm_broadcast.connect(websocket)
    try:
        snapshot = get_simulator().snapshot()
        await websocket.send_text(snapshot.model_dump_json())
        while True:
            # Keep the socket alive; clients are receive-only for now.
            await websocket.receive_text()
    except WebSocketDisconnect:
        pass
    finally:
        await storm_broadcast.disconnect(websocket)
