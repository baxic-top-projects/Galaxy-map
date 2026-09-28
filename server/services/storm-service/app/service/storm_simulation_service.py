from __future__ import annotations

import hashlib
import os
import random
import threading
from collections import deque
from concurrent.futures import ProcessPoolExecutor
from datetime import datetime, timezone
from typing import Any, Iterable

from app.config.settings import Settings
from app.dto.storm import (
    AffectedSystemDto,
    StormDto,
    StormSnapshotDto,
    StormStage,
    StormType,
    SystemStormStateDto,
)
from app.service.galaxy_graph_service import GalaxyGraphService

STORM_PALETTE: dict[StormType, str] = {
    "electric": "#6ec8ff",
    "gravity": "#c28cff",
    "particle": "#ffd27a",
    "shroud": "#7dffc4",
}

STORM_TYPES: tuple[StormType, ...] = ("electric", "gravity", "particle", "shroud")

# Process-pool worker state (initialized once per child process).
_WORKER_ADJACENCY: dict[str, list[str]] = {}
_WORKER_SETTINGS: dict[str, Any] = {}


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _init_storm_worker(adjacency: dict[str, list[str]], settings_payload: dict[str, Any]) -> None:
    global _WORKER_ADJACENCY, _WORKER_SETTINGS
    _WORKER_ADJACENCY = adjacency
    _WORKER_SETTINGS = settings_payload


def _systems_within_hops(origin_id: str, max_hops: int, adjacency: dict[str, list[str]]) -> dict[str, int]:
    hops = {origin_id: 0}
    queue: deque[str] = deque([origin_id])
    while queue:
        current = queue.popleft()
        current_hops = hops[current]
        if current_hops >= max_hops:
            continue
        for neighbor in adjacency.get(current, ()):
            if neighbor in hops:
                continue
            hops[neighbor] = current_hops + 1
            queue.append(neighbor)
    return hops


def _refresh_affected_payload(storm: dict[str, Any], adjacency: dict[str, list[str]]) -> dict[str, Any]:
    hops = _systems_within_hops(storm["originSystemId"], int(storm["radiusHops"]), adjacency)
    affected = []
    for system_id, hop in sorted(hops.items(), key=lambda item: (item[1], item[0])):
        falloff = 1.0 / (1.0 + hop * 0.55)
        intensity = round(min(1.0, float(storm["intensity"]) * falloff), 4)
        affected.append(
            {
                "systemId": system_id,
                "intensity": intensity,
                "hopsFromOrigin": hop,
            }
        )
    storm = dict(storm)
    storm["affectedSystems"] = affected
    return storm


def _advance_storm_payload(storm: dict[str, Any]) -> dict[str, Any] | None:
    settings = _WORKER_SETTINGS
    age = int(storm["ageTicks"]) + 1
    form_end = int(settings["form_ticks"])
    active_ticks = int(settings["active_ticks"])
    dissipate_ticks = int(settings["dissipate_ticks"])
    max_radius_hops = int(settings["max_radius_hops"])
    active_end = form_end + active_ticks
    dissipate_end = active_end + dissipate_ticks
    if age >= dissipate_end:
        return None

    if age < form_end:
        stage: StormStage = "forming"
        intensity = 0.25 + 0.35 * (age / max(form_end, 1))
        radius = 0
    elif age < active_end:
        stage = "active"
        active_age = age - form_end
        intensity = 0.65 + 0.3 * min(1.0, active_age / max(active_ticks * 0.4, 1))
        radius = min(
            max_radius_hops,
            1 + active_age // max(active_ticks // max(max_radius_hops, 1), 1),
        )
    else:
        stage = "dissipating"
        dissipate_age = age - active_end
        intensity = max(0.08, 0.7 * (1.0 - dissipate_age / max(dissipate_ticks, 1)))
        radius = max(0, int(storm["radiusHops"]) - (1 if dissipate_age % 2 == 0 else 0))

    updated = dict(storm)
    updated.update(
        {
            "ageTicks": age,
            "stage": stage,
            "intensity": round(min(1.0, intensity), 4),
            "radiusHops": radius,
        }
    )
    return _refresh_affected_payload(updated, _WORKER_ADJACENCY)


class StormSimulationService:
    """Server-side timed storm lifecycle over the hypercorridor graph."""

    def __init__(self, graph: GalaxyGraphService, settings: Settings):
        self.graph = graph
        self.settings = settings
        self.rng = random.Random(settings.seed)
        self.tick = 0
        self.storms: list[StormDto] = []
        self._lock = threading.RLock()
        self._counter = 0
        self._adjacency = {key: list(values) for key, values in graph.adjacency.items()}
        for system_id in graph.systems:
            self._adjacency.setdefault(system_id, [])
        workers = settings.worker_processes
        if workers <= 0:
            workers = max(1, os.cpu_count() or 1)
        self._workers = workers
        self._pool: ProcessPoolExecutor | None = None
        if workers > 1:
            self._pool = ProcessPoolExecutor(
                max_workers=workers,
                initializer=_init_storm_worker,
                initargs=(
                    self._adjacency,
                    {
                        "form_ticks": settings.form_ticks,
                        "active_ticks": settings.active_ticks,
                        "dissipate_ticks": settings.dissipate_ticks,
                        "max_radius_hops": settings.max_radius_hops,
                    },
                ),
            )

    def close(self) -> None:
        if self._pool:
            self._pool.shutdown(wait=False, cancel_futures=True)
            self._pool = None

    def snapshot(self) -> StormSnapshotDto:
        with self._lock:
            return StormSnapshotDto(
                tick=self.tick,
                generatedAt=_utc_now(),
                storms=[storm.model_copy(deep=True) for storm in self.storms],
                systems=self._system_states(self.storms),
            )

    def system_state(self, system_id: str) -> SystemStormStateDto | None:
        with self._lock:
            for state in self._system_states(self.storms):
                if state.systemId == system_id:
                    return state
        return None

    def step(self) -> StormSnapshotDto:
        with self._lock:
            self.tick += 1
            payloads = [storm.model_dump(mode="json") for storm in self.storms]
            advanced = self._advance_many(payloads)
            surviving = [StormDto.model_validate(item) for item in advanced if item is not None]
            self.storms = surviving
            if (
                len(self.storms) < self.settings.max_active_storms
                and self.rng.random() < self.settings.spawn_chance
            ):
                spawned = self._spawn_storm()
                if spawned is not None:
                    self.storms.append(spawned)
            return self.snapshot()

    def _advance_many(self, payloads: list[dict[str, Any]]) -> list[dict[str, Any] | None]:
        if not payloads:
            return []
        if self._pool is None or len(payloads) == 1:
            _init_storm_worker(
                self._adjacency,
                {
                    "form_ticks": self.settings.form_ticks,
                    "active_ticks": self.settings.active_ticks,
                    "dissipate_ticks": self.settings.dissipate_ticks,
                    "max_radius_hops": self.settings.max_radius_hops,
                },
            )
            return [_advance_storm_payload(item) for item in payloads]
        return list(self._pool.map(_advance_storm_payload, payloads, chunksize=1))

    def _spawn_storm(self) -> StormDto | None:
        occupied = {
            system.systemId for storm in self.storms for system in storm.affectedSystems
        }
        candidates = [system_id for system_id in self.graph.seed_ids if system_id not in occupied]
        if not candidates:
            return None
        origin = self.rng.choice(candidates)
        storm_type = self.rng.choice(STORM_TYPES)
        self._counter += 1
        digest = hashlib.sha1(
            f"{self.settings.seed}:{self.tick}:{origin}:{self._counter}".encode()
        ).hexdigest()[:10]
        storm = StormDto(
            id=f"storm-{digest}",
            type=storm_type,
            stage="forming",
            originSystemId=origin,
            intensity=0.35,
            radiusHops=0,
            ageTicks=0,
            color=STORM_PALETTE[storm_type],
            affectedSystems=[],
        )
        refreshed = _refresh_affected_payload(storm.model_dump(mode="json"), self._adjacency)
        return StormDto.model_validate(refreshed)

    def _system_states(self, storms: Iterable[StormDto]) -> list[SystemStormStateDto]:
        strongest: dict[str, SystemStormStateDto] = {}
        for storm in storms:
            for affected in storm.affectedSystems:
                current = strongest.get(affected.systemId)
                if current and current.intensity >= affected.intensity:
                    continue
                strongest[affected.systemId] = SystemStormStateDto(
                    systemId=affected.systemId,
                    intensity=affected.intensity,
                    stage=storm.stage,
                    type=storm.type,
                    stormId=storm.id,
                    color=storm.color,
                )
        return [strongest[key] for key in sorted(strongest)]
