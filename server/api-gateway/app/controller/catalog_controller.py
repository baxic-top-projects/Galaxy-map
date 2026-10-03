from __future__ import annotations

from typing import Annotated
from urllib.parse import urlencode

from fastapi import APIRouter, Body, Depends, Response
from pydantic import BaseModel, Field

from app.service.catalog_client_service import catalog_client
from app.security import require_admin

router = APIRouter()


class SystemOwnerUpdate(BaseModel):
    stem: str = Field(min_length=1, max_length=255)


@router.get("/api/v1/galaxy")
async def galaxy_index():
    response = await catalog_client.request("GET", "/internal/v1/galaxy")
    return Response(
        content=response.content,
        status_code=response.status_code,
        media_type="application/json",
    )


@router.get("/api/v1/galaxy/map")
async def galaxy_map():
    response = await catalog_client.request("GET", "/internal/v1/galaxy/map")
    return Response(
        content=response.content,
        status_code=response.status_code,
        media_type="application/json",
    )


@router.get("/api/v1/galaxy/systems")
async def galaxy_systems(tx: int, ty: int):
    path = f"/internal/v1/galaxy/systems?{urlencode({'tx': tx, 'ty': ty})}"
    response = await catalog_client.request("GET", path)
    return Response(
        content=response.content,
        status_code=response.status_code,
        media_type="application/json",
    )


@router.get("/api/v1/galaxy/edges")
async def galaxy_edges():
    response = await catalog_client.request("GET", "/internal/v1/galaxy/edges")
    return Response(
        content=response.content,
        status_code=response.status_code,
        media_type="application/json",
    )


@router.get("/api/v1/galaxy/search")
async def galaxy_search():
    response = await catalog_client.request("GET", "/internal/v1/galaxy/search")
    return Response(
        content=response.content,
        status_code=response.status_code,
        media_type="application/json",
    )


@router.patch("/api/v1/systems/{system_id:path}/owner")
async def system_owner(
    system_id: str,
    payload: Annotated[SystemOwnerUpdate, Body()],
    _admin: Annotated[dict, Depends(require_admin)],
):
    response = await catalog_client.request(
        "PATCH",
        f"/internal/v1/systems/{system_id}/owner",
        json={"stem": payload.stem},
    )
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
