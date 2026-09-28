from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.config.settings import settings
from app.controller.health_controller import router as health_router
from app.controller.storm_controller import router as storm_router
from app.service.catalog_client_service import fetch_galaxy_index
from app.service.galaxy_graph_service import GalaxyGraphService
from app.service.storm_broadcast_service import storm_broadcast
from app.service.storm_kafka_service import storm_kafka
from app.service.storm_simulation_service import StormSimulationService

simulator: StormSimulationService | None = None
_tick_task: asyncio.Task | None = None
_publish_tasks: set[asyncio.Task] = set()


def _schedule_kafka_publish(payload: dict) -> None:
    """Publish to Kafka asynchronously without blocking the tick / WS path."""
    if not storm_kafka.enabled:
        return

    async def _run() -> None:
        await storm_kafka.publish_snapshot(payload)

    task = asyncio.create_task(_run(), name="storm-kafka-publish")
    _publish_tasks.add(task)
    task.add_done_callback(_publish_tasks.discard)


async def _tick_loop(sim: StormSimulationService) -> None:
    while True:
        await asyncio.sleep(settings.tick_seconds)
        await asyncio.to_thread(sim.step)
        payload = sim.public_snapshot()
        await storm_broadcast.broadcast_json(payload)
        _schedule_kafka_publish(payload)


@asynccontextmanager
async def lifespan(_app: FastAPI):
    global simulator, _tick_task
    payload = await asyncio.to_thread(fetch_galaxy_index, settings)
    graph = GalaxyGraphService(payload)
    simulator = StormSimulationService(graph, settings)
    await storm_kafka.start()
    await asyncio.to_thread(simulator.step)
    first_payload = simulator.public_snapshot()
    await storm_broadcast.broadcast_json(first_payload)
    _schedule_kafka_publish(first_payload)
    _tick_task = asyncio.create_task(_tick_loop(simulator))
    yield
    if _tick_task:
        _tick_task.cancel()
        try:
            await _tick_task
        except asyncio.CancelledError:
            pass
    if _publish_tasks:
        await asyncio.gather(*list(_publish_tasks), return_exceptions=True)
        _publish_tasks.clear()
    await storm_kafka.stop()
    if simulator:
        simulator.close()
    simulator = None
    _tick_task = None


app = FastAPI(title="Galaxy Storm Service", version="1.0.0", lifespan=lifespan)
app.include_router(health_router)
app.include_router(storm_router)
