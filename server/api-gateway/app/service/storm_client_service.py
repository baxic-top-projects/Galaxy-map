from __future__ import annotations

import httpx
from fastapi import HTTPException

from app.config.settings import settings


class StormClientService:
    """HTTP client that calls the internal storm-service API."""

    def __init__(self, base_url: str | None = None, timeout: float | None = None):
        self.base_url = (base_url or settings.storm_service_url).rstrip("/")
        self.timeout = timeout if timeout is not None else settings.request_timeout_seconds

    async def request(self, method: str, path: str) -> httpx.Response:
        url = f"{self.base_url}{path}"
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                return await client.request(method, url)
        except httpx.RequestError as exc:
            raise HTTPException(status_code=502, detail=f"Storm service unreachable: {exc}") from exc


storm_client = StormClientService()
