from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI

from app.config.settings import settings
from app.controller.health_controller import router as health_router
from app.controller.storm_controller import router as storm_router
from app.service.galaxy_graph_service import GalaxyGraphService
from app.service.storm_broadcast_service import storm_broadcast
from app.service.storm_simulation_service import StormSimulationService

simulator: StormSimulationService | None = None
_tick_task: asyncio.Task | None = None


async def _tick_loop(sim: StormSimulationService) -> None:
    while True:
        await asyncio.sleep(settings.tick_seconds)
        snapshot = await asyncio.to_thread(sim.step)
        await storm_broadcast.broadcast_json(snapshot.model_dump(mode="json"))


@asynccontextmanager
async def lifespan(_app: FastAPI):
    global simulator, _tick_task
    index_path = Path(settings.galaxy_index_path)
    if not index_path.is_file():
        raise RuntimeError(f"Galaxy index not found: {index_path}")
    graph = GalaxyGraphService(index_path)
    simulator = StormSimulationService(graph, settings)
    first = simulator.step()
    await storm_broadcast.broadcast_json(first.model_dump(mode="json"))
    _tick_task = asyncio.create_task(_tick_loop(simulator))
    yield
    if _tick_task:
        _tick_task.cancel()
        try:
            await _tick_task
        except asyncio.CancelledError:
            pass
    simulator = None
    _tick_task = None


app = FastAPI(title="Galaxy Storm Service", version="1.0.0", lifespan=lifespan)
app.include_router(health_router)
app.include_router(storm_router)
