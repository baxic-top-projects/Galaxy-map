from __future__ import annotations

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="ASSET_", env_file=".env", extra="ignore")

    host: str = "0.0.0.0"
    port: int = 8002

    # S3 / S3-compatible object storage
    s3_bucket: str = "galaxy-map-assets"
    s3_region: str = "ru-central1"
    s3_endpoint_url: str = ""
    s3_access_key_id: str = ""
    s3_secret_access_key: str = ""
    s3_force_path_style: bool = False
    s3_prefix: str = "models/"

    # Browser-facing base URL (CDN or public bucket URL). No trailing slash.
    # Example: https://storage.yandexcloud.net/galaxy-map-assets
    # Example: https://cdn.galaxy.baxic.ru
    s3_public_base_url: str = ""

    # If true, manifest URLs are short-lived presigned GET links.
    # Use for private buckets. Prefer public CDN + false for production maps.
    presign_enabled: bool = False
    presign_ttl_seconds: int = 3600

    # Cache listed objects in memory.
    manifest_cache_seconds: float = 60.0


settings = Settings()
