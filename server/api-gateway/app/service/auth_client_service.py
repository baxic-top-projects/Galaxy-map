from __future__ import annotations

import httpx
from fastapi import HTTPException

from app.config.settings import settings


class AuthClientService:
    def __init__(self, base_url: str | None = None, timeout: float | None = None):
        self.base_url = (base_url or settings.auth_service_url).rstrip("/")
        self.timeout = timeout if timeout is not None else settings.request_timeout_seconds

    async def request(
        self,
        method: str,
        path: str,
        *,
        headers: dict[str, str] | None = None,
        params: dict[str, str] | None = None,
        content: bytes | None = None,
    ) -> httpx.Response:
        url = f"{self.base_url}{path}"
        forwarded = dict(headers or {})
        if settings.internal_service_token:
            forwarded["X-Internal-Service-Token"] = settings.internal_service_token
        try:
            async with httpx.AsyncClient(timeout=self.timeout, follow_redirects=False) as client:
                return await client.request(
                    method,
                    url,
                    headers=forwarded,
                    params=params,
                    content=content,
                )
        except httpx.RequestError as exc:
            raise HTTPException(status_code=502, detail=f"Auth service unreachable: {exc}") from exc


auth_client = AuthClientService()
