from __future__ import annotations

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="GATEWAY_", env_file=".env", extra="ignore")

    storm_service_url: str = "http://storm-service:8001"
    asset_service_url: str = "http://asset-service:8002"
    catalog_service_url: str = "http://catalog-service:8003"
    auth_service_url: str = "http://auth-service:8004"
    internal_service_token: str = ""
    refresh_cookie_secure: bool = True
    refresh_cookie_domain: str = ""
    refresh_cookie_max_age: int = 60 * 60 * 24 * 30
    cors_origins: str = (
        "http://localhost:5173,http://127.0.0.1:5173,"
        "http://localhost:9999,http://127.0.0.1:9999"
    )
    host: str = "0.0.0.0"
    port: int = 8000
    request_timeout_seconds: float = 30.0


settings = Settings()
