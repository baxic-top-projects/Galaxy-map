from __future__ import annotations

import json

from fastapi import Header, HTTPException

from app.service.auth_client_service import auth_client


async def require_admin(authorization: str | None = Header(default=None)) -> dict:
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(status_code=401, detail="Authentication required")
    response = await auth_client.request(
        "GET",
        "/internal/v1/auth/authorize/admin",
        headers={"Authorization": authorization},
    )
    if response.status_code == 401:
        raise HTTPException(status_code=401, detail="Invalid or expired access token")
    if response.status_code == 403:
        raise HTTPException(status_code=403, detail="Administrator role required")
    if response.status_code >= 400:
        raise HTTPException(status_code=502, detail="Authorization service failed")
    try:
        return response.json()
    except (json.JSONDecodeError, ValueError) as exc:
        raise HTTPException(status_code=502, detail="Invalid authorization response") from exc
