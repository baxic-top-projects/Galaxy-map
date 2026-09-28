from __future__ import annotations

from fastapi import APIRouter, Response

from app.service.asset_client_service import asset_client

router = APIRouter()


@router.get("/api/v1/assets/manifest")
async def assets_manifest(force: bool = False):
    suffix = "?force=true" if force else ""
    response = await asset_client.request("GET", f"/internal/v1/assets/manifest{suffix}")
    return Response(
        content=response.content,
        status_code=response.status_code,
        media_type="application/json",
    )


@router.get("/api/v1/assets/models/{kind}/{key}")
async def assets_resolve(kind: str, key: str):
    response = await asset_client.request("GET", f"/internal/v1/assets/models/{kind}/{key}")
    return Response(
        content=response.content,
        status_code=response.status_code,
        media_type="application/json",
    )
