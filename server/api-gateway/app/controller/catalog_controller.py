from __future__ import annotations

from fastapi import APIRouter, Response

from app.service.catalog_client_service import catalog_client

router = APIRouter()


@router.get("/api/v1/galaxy")
async def galaxy_index():
    response = await catalog_client.request("GET", "/internal/v1/galaxy")
    return Response(
        content=response.content,
        status_code=response.status_code,
        media_type="application/json",
    )


@router.get("/api/v1/systems/{system_id:path}")
async def system_detail(system_id: str):
    response = await catalog_client.request("GET", f"/internal/v1/systems/{system_id}")
    return Response(
        content=response.content,
        status_code=response.status_code,
        media_type="application/json",
    )
