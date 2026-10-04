from __future__ import annotations

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="STORM_", env_file=".env", extra="ignore")

    catalog_service_url: str = "http://catalog-service:8003"
    catalog_timeout_seconds: float = 60.0
    seed: int = 20260928
    tick_seconds: float = 2.0
    max_active_storms: int = 8
    # Used when model is disabled or /invocations fails.
    spawn_chance: float = 0.35
    form_ticks: int = 4
    active_ticks: int = 18
    dissipate_ticks: int = 8
    max_radius_hops: int = 2
    # Ticks to crawl one hyperlane segment (higher = slower Stellaris-like travel).
    move_interval_ticks: int = 3
    # Planned travel distance for a new storm path.
    path_hops_min: int = 6
    path_hops_max: int = 16
    host: str = "0.0.0.0"
    port: int = 8001
    # 0/1 = single process (asyncio keeps WS free; no CPU parallelism).
    # >1 = ProcessPoolExecutor across storm advances.
    worker_processes: int = 0
    kafka_bootstrap_servers: str = "kafka:9092"
    kafka_topic: str = "galaxy.storms"
    kafka_enabled: bool = True
    # MLflow stormmodel scoring (https://stormmodel.baxic.ru). Empty URL = random spawn.
    model_enabled: bool = True
    model_url: str = ""
    model_username: str = "model-api"
    model_password: str = ""
    model_timeout_seconds: float = 10.0


settings = Settings()
