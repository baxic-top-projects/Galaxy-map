from __future__ import annotations

import hashlib
import random
import threading
from datetime import datetime, timezone
from typing import Iterable

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


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


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
            surviving: list[StormDto] = []
            for storm in self.storms:
                updated = self._advance_storm(storm)
                if updated is not None:
                    surviving.append(updated)
            self.storms = surviving
            if (
                len(self.storms) < self.settings.max_active_storms
                and self.rng.random() < self.settings.spawn_chance
            ):
                spawned = self._spawn_storm()
                if spawned is not None:
                    self.storms.append(spawned)
            return self.snapshot()

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
        return self._refresh_affected(storm)

    def _advance_storm(self, storm: StormDto) -> StormDto | None:
        age = storm.ageTicks + 1
        form_end = self.settings.form_ticks
        active_end = form_end + self.settings.active_ticks
        dissipate_end = active_end + self.settings.dissipate_ticks
        if age >= dissipate_end:
            return None

        if age < form_end:
            stage: StormStage = "forming"
            intensity = 0.25 + 0.35 * (age / max(form_end, 1))
            radius = 0
        elif age < active_end:
            stage = "active"
            active_age = age - form_end
            intensity = 0.65 + 0.3 * min(1.0, active_age / max(self.settings.active_ticks * 0.4, 1))
            radius = min(
                self.settings.max_radius_hops,
                1
                + active_age
                // max(self.settings.active_ticks // max(self.settings.max_radius_hops, 1), 1),
            )
        else:
            stage = "dissipating"
            dissipate_age = age - active_end
            intensity = max(
                0.08,
                0.7 * (1.0 - dissipate_age / max(self.settings.dissipate_ticks, 1)),
            )
            radius = max(0, storm.radiusHops - (1 if dissipate_age % 2 == 0 else 0))

        updated = storm.model_copy(
            update={
                "ageTicks": age,
                "stage": stage,
                "intensity": round(min(1.0, intensity), 4),
                "radiusHops": radius,
            }
        )
        return self._refresh_affected(updated)

    def _refresh_affected(self, storm: StormDto) -> StormDto:
        hops = self.graph.systems_within_hops(storm.originSystemId, storm.radiusHops)
        affected = []
        for system_id, hop in sorted(hops.items(), key=lambda item: (item[1], item[0])):
            falloff = 1.0 / (1.0 + hop * 0.55)
            intensity = round(min(1.0, storm.intensity * falloff), 4)
            affected.append(
                AffectedSystemDto(
                    systemId=system_id,
                    intensity=intensity,
                    hopsFromOrigin=hop,
                )
            )
        storm.affectedSystems = affected
        return storm

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
