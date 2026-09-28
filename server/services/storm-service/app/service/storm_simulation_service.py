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


def _worker_settings_payload(settings: Settings) -> dict[str, Any]:
    return {
        "form_ticks": settings.form_ticks,
        "active_ticks": settings.active_ticks,
        "dissipate_ticks": settings.dissipate_ticks,
        "max_radius_hops": settings.max_radius_hops,
        "move_interval_ticks": settings.move_interval_ticks,
    }


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


def _shortest_path(adjacency: dict[str, list[str]], start: str, end: str) -> list[str]:
    if start == end:
        return [start]
    parent: dict[str, str | None] = {start: None}
    queue: deque[str] = deque([start])
    while queue:
        current = queue.popleft()
        for neighbor in adjacency.get(current, ()):
            if neighbor in parent:
                continue
            parent[neighbor] = current
            if neighbor == end:
                queue.clear()
                break
            queue.append(neighbor)
    if end not in parent:
        return [start]
    path = [end]
    while path[-1] != start:
        prev = parent[path[-1]]
        if prev is None:
            break
        path.append(prev)
    path.reverse()
    return path


def _build_travel_path(
    adjacency: dict[str, list[str]],
    origin: str,
    rng: random.Random,
    hops_min: int,
    hops_max: int,
) -> list[str]:
    """Pick a distant system along hyperlanes and return the travel route."""
    distances = _systems_within_hops(origin, max(hops_max, hops_min), adjacency)
    band = [
        system_id
        for system_id, hops in distances.items()
        if hops_min <= hops <= hops_max and system_id != origin
    ]
    if not band:
        band = [system_id for system_id, hops in distances.items() if hops >= 2 and system_id != origin]
    if not band:
        neighbors = list(adjacency.get(origin, ()))
        if neighbors:
            return [origin, rng.choice(neighbors)]
        return [origin]
    destination = rng.choice(band)
    path = _shortest_path(adjacency, origin, destination)
    return path if path else [origin]


def _extend_travel_path(
    adjacency: dict[str, list[str]],
    current: str,
    visited: set[str],
    rng: random.Random,
    hops_min: int,
    hops_max: int,
) -> list[str]:
    """Continue wandering when the planned path ends while still active."""
    extension = _build_travel_path(adjacency, current, rng, hops_min, hops_max)
    if len(extension) <= 1:
        # Prefer an unvisited neighbor, else any neighbor.
        neighbors = list(adjacency.get(current, ()))
        if not neighbors:
            return [current]
        unseen = [node for node in neighbors if node not in visited]
        nxt = rng.choice(unseen or neighbors)
        return [current, nxt]
    return extension


def _refresh_affected_payload(storm: dict[str, Any], adjacency: dict[str, list[str]]) -> dict[str, Any]:
    path = list(storm.get("path") or [storm["originSystemId"]])
    path_index = int(storm.get("pathIndex") or 0)
    path_index = max(0, min(path_index, len(path) - 1))
    progress = float(storm.get("pathProgress") or 0.0)
    from_id = path[path_index]
    to_id = path[path_index + 1] if path_index + 1 < len(path) else from_id
    # AoE follows the eye: after the midpoint of a hop, influence shifts to the destination.
    center = to_id if (to_id != from_id and progress >= 0.5) else from_id
    hops = _systems_within_hops(center, int(storm["radiusHops"]), adjacency)
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
    storm["path"] = path
    storm["pathIndex"] = path_index
    storm["pathProgress"] = max(0.0, min(1.0, progress))
    storm["currentSystemId"] = from_id
    storm["nextSystemId"] = to_id
    storm["affectedSystems"] = affected
    return storm


def _advance_storm_payload(storm: dict[str, Any]) -> dict[str, Any] | None:
    settings = _WORKER_SETTINGS
    age = int(storm["ageTicks"]) + 1
    form_end = int(settings["form_ticks"])
    active_ticks = int(settings["active_ticks"])
    dissipate_ticks = int(settings["dissipate_ticks"])
    max_radius_hops = int(settings["max_radius_hops"])
    # Ticks required to travel one hyperlane segment (Stellaris-like crawl).
    move_interval = max(1, int(settings.get("move_interval_ticks", 3)))
    active_end = form_end + active_ticks
    dissipate_end = active_end + dissipate_ticks
    if age >= dissipate_end:
        return None

    path = list(storm.get("path") or [storm["originSystemId"]])
    path_index = int(storm.get("pathIndex") or 0)
    path_index = max(0, min(path_index, len(path) - 1))
    path_progress = float(storm.get("pathProgress") or 0.0)
    current = path[path_index]

    def crawl_along_path(*, step: float) -> None:
        nonlocal path, path_index, path_progress, current
        if path_index >= len(path) - 1:
            return
        path_progress += step
        while path_progress >= 1.0 and path_index < len(path) - 1:
            path_progress -= 1.0
            path_index += 1
            current = path[path_index]
        if path_index >= len(path) - 1:
            path_progress = 0.0
            current = path[path_index]

    if age < form_end:
        stage: StormStage = "forming"
        intensity = 0.25 + 0.35 * (age / max(form_end, 1))
        radius = 0 if age < max(1, form_end // 2) else min(1, max_radius_hops)
        path_progress = 0.0
    elif age < active_end:
        stage = "active"
        active_age = age - form_end
        intensity = 0.65 + 0.3 * min(1.0, active_age / max(active_ticks * 0.4, 1))
        radius = min(max_radius_hops, max(1, max_radius_hops))
        crawl_along_path(step=1.0 / move_interval)
        if path_index >= len(path) - 1:
            # Path exhausted mid-life: wander onward from the front.
            seed = int(hashlib.sha1(f"{storm['id']}:{age}".encode()).hexdigest()[:8], 16)
            rng = random.Random(seed)
            extension = _extend_travel_path(
                _WORKER_ADJACENCY,
                current,
                set(path),
                rng,
                hops_min=3,
                hops_max=8,
            )
            if len(extension) > 1:
                path = path + extension[1:]
                # Start crawling the new segment immediately.
                crawl_along_path(step=1.0 / move_interval)
    else:
        stage = "dissipating"
        dissipate_age = age - active_end
        intensity = max(0.08, 0.7 * (1.0 - dissipate_age / max(dissipate_ticks, 1)))
        radius = max(0, int(storm["radiusHops"]) - (1 if dissipate_age % 2 == 0 else 0))
        crawl_along_path(step=1.0 / (move_interval + 1))

    updated = dict(storm)
    updated.update(
        {
            "ageTicks": age,
            "stage": stage,
            "intensity": round(min(1.0, intensity), 4),
            "radiusHops": radius,
            "path": path,
            "pathIndex": path_index,
            "pathProgress": round(max(0.0, min(1.0, path_progress)), 4),
            "currentSystemId": current,
            "nextSystemId": path[path_index + 1] if path_index + 1 < len(path) else current,
        }
    )
    return _refresh_affected_payload(updated, _WORKER_ADJACENCY)


class StormSimulationService:
    """Migrating galactic storms that travel along hypercorridors (Stellaris-like)."""

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
                initargs=(self._adjacency, _worker_settings_payload(settings)),
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
        payload_settings = _worker_settings_payload(self.settings)
        if self._pool is None or len(payloads) == 1:
            _init_storm_worker(self._adjacency, payload_settings)
            return [_advance_storm_payload(item) for item in payloads]
        return list(self._pool.map(_advance_storm_payload, payloads, chunksize=1))

    def _spawn_storm(self) -> StormDto | None:
        occupied = {
            system.systemId for storm in self.storms for system in storm.affectedSystems
        }
        occupied |= {storm.currentSystemId for storm in self.storms}
        candidates = [system_id for system_id in self.graph.seed_ids if system_id not in occupied]
        if not candidates:
            return None
        # Prefer connected systems so storms can travel.
        connected = [system_id for system_id in candidates if self._adjacency.get(system_id)]
        origin = self.rng.choice(connected or candidates)
        storm_type = self.rng.choice(STORM_TYPES)
        self._counter += 1
        digest = hashlib.sha1(
            f"{self.settings.seed}:{self.tick}:{origin}:{self._counter}".encode()
        ).hexdigest()[:10]
        path = _build_travel_path(
            self._adjacency,
            origin,
            self.rng,
            self.settings.path_hops_min,
            self.settings.path_hops_max,
        )
        storm = StormDto(
            id=f"storm-{digest}",
            type=storm_type,
            stage="forming",
            originSystemId=origin,
            currentSystemId=origin,
            nextSystemId=path[1] if len(path) > 1 else origin,
            path=path,
            pathIndex=0,
            pathProgress=0.0,
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
