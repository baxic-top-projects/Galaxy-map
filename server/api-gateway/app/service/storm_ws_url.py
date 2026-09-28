from __future__ import annotations

from urllib.parse import urlparse

from app.config.settings import settings


def storm_ws_url(path: str = "/internal/v1/storms/ws") -> str:
    parsed = urlparse(settings.storm_service_url)
    scheme = "wss" if parsed.scheme == "https" else "ws"
    netloc = parsed.netloc or parsed.path
    return f"{scheme}://{netloc}{path}"
