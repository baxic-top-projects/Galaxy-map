from __future__ import annotations

from functools import lru_cache

from pydantic import AnyHttpUrl, EmailStr, SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


def normalize_database_url(value: str) -> str:
    url = value.strip()
    if url.startswith("postgres://"):
        return "postgresql+psycopg://" + url[len("postgres://") :]
    if url.startswith("postgresql://") and "+" not in url.split("://", 1)[0]:
        return "postgresql+psycopg://" + url[len("postgresql://") :]
    return url


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="AUTH_", env_file=".env", extra="ignore", env_ignore_empty=True
    )

    host: str = "0.0.0.0"
    port: int = 8004
    database_url: str = "postgresql+psycopg://galaxy:galaxy@postgres:5432/galaxy"
    jwt_secret: SecretStr = SecretStr("change-me-in-production")
    jwt_issuer: str = "galaxy-auth"
    jwt_audience: str = "galaxy-services"
    access_token_minutes: int = 15
    refresh_token_days: int = 30
    email_token_minutes: int = 15
    reset_token_minutes: int = 15
    exchange_code_minutes: int = 2
    internal_service_token: SecretStr = SecretStr("")
    frontend_url: AnyHttpUrl = "http://localhost:3000"

    smtp_host: str = ""
    smtp_port: int = 587
    smtp_username: str = ""
    smtp_password: SecretStr = SecretStr("")
    smtp_from: EmailStr = "no-reply@example.com"
    smtp_from_name: str = "Galaxy Map"
    smtp_starttls: bool = True
    smtp_ssl: bool = False

    google_client_id: str = ""
    google_client_secret: SecretStr = SecretStr("")
    google_redirect_uri: AnyHttpUrl = "http://localhost:8000/api/v1/auth/google/callback"
    google_authorize_url: AnyHttpUrl = "https://accounts.google.com/o/oauth2/v2/auth"
    google_token_url: AnyHttpUrl = "https://oauth2.googleapis.com/token"
    google_userinfo_url: AnyHttpUrl = "https://openidconnect.googleapis.com/v1/userinfo"

    s3_bucket: str = ""
    s3_region: str = "ru-central1"
    s3_endpoint_url: str = ""
    s3_access_key_id: str = ""
    s3_secret_access_key: SecretStr = SecretStr("")
    s3_public_base_url: str = ""
    s3_avatar_prefix: str = "avatars/"
    avatar_max_bytes: int = 5 * 1024 * 1024

    @field_validator("database_url", mode="before")
    @classmethod
    def normalize_db(cls, value: object) -> object:
        return normalize_database_url(value) if isinstance(value, str) else value

    @field_validator("access_token_minutes", "refresh_token_days", "email_token_minutes",
                     "reset_token_minutes", "exchange_code_minutes")
    @classmethod
    def positive_duration(cls, value: int) -> int:
        if value <= 0:
            raise ValueError("token duration must be positive")
        return value

    @property
    def frontend_url_value(self) -> str:
        return str(self.frontend_url).rstrip("/")


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
