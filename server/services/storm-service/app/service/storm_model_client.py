from __future__ import annotations

import logging
import math
from collections import deque
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Iterable, Sequence

import httpx

from app.config.settings import Settings
from app.dto.storm import StormDto, StormType, SystemStormStateDto

logger = logging.getLogger(__name__)

STORM_TYPES: tuple[StormType, ...] = ("electric", "gravity", "particle", "shroud")
STORM_STAGES = ("forming", "active", "dissipating")

# Must match FEATURE_COLUMNS from the training notebook / MLflow signature.
FEATURE_COLUMNS: tuple[str, ...] = (
    "tick",
    "active_storm_count",
    "affected_system_count",
    "mean_storm_intensity",
    "max_storm_intensity",
    "mean_radius_hops",
    "mean_system_intensity",
    "max_system_intensity",
    "ticks_since_spawn",
    "spawns_last_5_ticks",
    "hour_sin",
    "hour_cos",
    "stage_forming_count",
    "stage_active_count",
    "stage_dissipating_count",
    "type_electric_count",
    "type_gravity_count",
    "type_particle_count",
    "type_shroud_count",
)


@dataclass(frozen=True)
class SpawnDecision:
    should_spawn: bool
    storm_type: StormType | None
    spawn_probability: float | None
    source: str  # "model" | "fallback"


def _safe_mean(values: Iterable[float | None]) -> float:
    nums = [float(v) for v in values if v is not None]
    return sum(nums) / len(nums) if nums else 0.0


def _safe_max(values: Iterable[float | None]) -> float:
    nums = [float(v) for v in values if v is not None]
    return max(nums) if nums else 0.0


def build_spawn_features(
    *,
    tick: int,
    storms: Sequence[StormDto],
    systems: Sequence[SystemStormStateDto],
    ticks_since_spawn: int,
    spawns_last_5_ticks: int,
    now: datetime | None = None,
) -> dict[str, float]:
    """Build the same feature vector the MLflow model was trained on."""
    ts = now or datetime.now(timezone.utc)
    features: dict[str, float] = {
        "tick": float(tick),
        "active_storm_count": float(len(storms)),
        "affected_system_count": float(len(systems)),
        "mean_storm_intensity": _safe_mean(s.intensity for s in storms),
        "max_storm_intensity": _safe_max(s.intensity for s in storms),
        "mean_radius_hops": _safe_mean(float(s.radiusHops) for s in storms),
        "mean_system_intensity": _safe_mean(s.intensity for s in systems),
        "max_system_intensity": _safe_max(s.intensity for s in systems),
        "ticks_since_spawn": float(ticks_since_spawn),
        "spawns_last_5_ticks": float(spawns_last_5_ticks),
        "hour_sin": math.sin(2 * math.pi * ts.hour / 24),
        "hour_cos": math.cos(2 * math.pi * ts.hour / 24),
    }
    for stage in STORM_STAGES:
        features[f"stage_{stage}_count"] = float(sum(s.stage == stage for s in storms))
    for storm_type in STORM_TYPES:
        features[f"type_{storm_type}_count"] = float(sum(s.type == storm_type for s in storms))
    return features


def _parse_prediction(payload: Any) -> tuple[bool, StormType | None, float | None]:
    row: dict[str, Any] | None = None
    if isinstance(payload, list) and payload:
        first = payload[0]
        row = first if isinstance(first, dict) else None
    elif isinstance(payload, dict):
        if "predictions" in payload:
            preds = payload["predictions"]
            if isinstance(preds, list) and preds:
                first = preds[0]
                row = first if isinstance(first, dict) else None
            elif isinstance(preds, dict):
                row = preds
        elif "dataframe_records" in payload and isinstance(payload["dataframe_records"], list):
            first = payload["dataframe_records"][0]
            row = first if isinstance(first, dict) else None
        elif "spawn_probability" in payload or "should_spawn" in payload:
            row = payload

    if not row:
        raise ValueError(f"unexpected model response shape: {type(payload)!r}")

    prob_raw = row.get("spawn_probability")
    spawn_probability = float(prob_raw) if prob_raw is not None else None
    if "should_spawn" in row:
        should_spawn = bool(row["should_spawn"])
    elif spawn_probability is not None:
        should_spawn = spawn_probability >= 0.5
    else:
        raise ValueError("model response missing should_spawn/spawn_probability")

    predicted = row.get("predicted_type")
    storm_type: StormType | None = None
    if isinstance(predicted, str) and predicted in STORM_TYPES:
        storm_type = predicted  # type: ignore[assignment]
    return should_spawn, storm_type, spawn_probability


class StormModelClient:
    """HTTP client for stormmodel MLflow scoring server."""

    def __init__(self, settings: Settings):
        self.settings = settings
        self._recent_spawns: deque[int] = deque(maxlen=5)
        self._ticks_since_spawn = 100

    @property
    def enabled(self) -> bool:
        return bool(self.settings.model_url.strip()) and self.settings.model_enabled

    def note_spawn_outcome(self, spawned: bool) -> None:
        flag = 1 if spawned else 0
        self._recent_spawns.append(flag)
        self._ticks_since_spawn = 0 if spawned else min(self._ticks_since_spawn + 1, 100)

    def decide(
        self,
        *,
        tick: int,
        storms: Sequence[StormDto],
        systems: Sequence[SystemStormStateDto],
        fallback_chance: float,
        rng_roll: float,
    ) -> SpawnDecision:
        if not self.enabled:
            return SpawnDecision(
                should_spawn=rng_roll < fallback_chance,
                storm_type=None,
                spawn_probability=None,
                source="fallback",
            )

        features = build_spawn_features(
            tick=tick,
            storms=storms,
            systems=systems,
            ticks_since_spawn=self._ticks_since_spawn,
            spawns_last_5_ticks=sum(self._recent_spawns),
        )
        try:
            _model_should, storm_type, probability = self._invoke(features)
            p = float(probability) if probability is not None else 0.0
            # Empty map safety: never stay barren longer than the old random baseline.
            if len(storms) == 0:
                p = max(p, fallback_chance)
            mode = (self.settings.model_decision_mode or "probability").strip().lower()
            if mode == "threshold":
                should_spawn = p >= float(self.settings.model_spawn_threshold)
            else:
                should_spawn = rng_roll < p
            logger.info(
                "storm model tick=%s p=%.4f should=%s type=%s storms=%s mode=%s",
                tick,
                p,
                should_spawn,
                storm_type,
                len(storms),
                mode,
            )
            return SpawnDecision(
                should_spawn=should_spawn,
                storm_type=storm_type,
                spawn_probability=p,
                source="model",
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning("Storm model invoke failed; fallback to spawn_chance: %s", exc)
            return SpawnDecision(
                should_spawn=rng_roll < fallback_chance,
                storm_type=None,
                spawn_probability=None,
                source="fallback",
            )

    def _invoke(self, features: dict[str, float]) -> tuple[bool, StormType | None, float | None]:
        record = {key: features[key] for key in FEATURE_COLUMNS}
        url = f"{self.settings.model_url.rstrip('/')}/invocations"
        auth = None
        username = self.settings.model_username.strip()
        password = self.settings.model_password
        if username:
            auth = (username, password)
        with httpx.Client(timeout=self.settings.model_timeout_seconds) as client:
            response = client.post(
                url,
                json={"dataframe_records": [record]},
                auth=auth,
            )
            response.raise_for_status()
            return _parse_prediction(response.json())
