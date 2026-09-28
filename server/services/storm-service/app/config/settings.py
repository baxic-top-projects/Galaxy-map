from __future__ import annotations

from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="STORM_", env_file=".env", extra="ignore")

    galaxy_index_path: Path = Path("/data/galaxy-index.json")
    seed: int = 20260928
    tick_seconds: float = 2.0
    max_active_storms: int = 8
    spawn_chance: float = 0.35
    form_ticks: int = 4
    active_ticks: int = 18
    dissipate_ticks: int = 8
    max_radius_hops: int = 4
    host: str = "0.0.0.0"
    port: int = 8001
    # Reserved for future event bus integration.
    kafka_bootstrap_servers: str = "kafka:9092"


settings = Settings()
