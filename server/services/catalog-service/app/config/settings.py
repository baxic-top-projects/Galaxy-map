from __future__ import annotations

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


def normalize_database_url(url: str) -> str:
    value = (url or "").strip()
    if value.startswith("postgres://"):
        value = "postgresql+psycopg://" + value[len("postgres://") :]
    elif value.startswith("postgresql://") and "+psycopg" not in value.split("://", 1)[0]:
        value = "postgresql+psycopg://" + value[len("postgresql://") :]
    # Neon and most cloud Postgres require TLS.
    if "sslmode=" not in value and "neon.tech" in value:
        sep = "&" if "?" in value else "?"
        value = f"{value}{sep}sslmode=require"
    return value


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="CATALOG_", env_file=".env", extra="ignore")

    host: str = "0.0.0.0"
    port: int = 8003
    database_url: str = "postgresql+psycopg://galaxy:galaxy@postgres:5432/galaxy"
    galaxy_index_path: str = "/data/galaxy-index.json"
    systems_dir: str = "/data/systems"
    seed_on_startup: bool = True
    # When false (default), only insert missing systems + refresh index tables.
    # Set true to rewrite every system row from JSON on each boot.
    seed_full_sync: bool = False

    @field_validator("database_url", mode="before")
    @classmethod
    def _normalize_db_url(cls, value: object) -> object:
        if isinstance(value, str):
            return normalize_database_url(value)
        return value


settings = Settings()
