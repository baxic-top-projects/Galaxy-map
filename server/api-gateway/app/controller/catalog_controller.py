from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Body, Response
from pydantic import BaseModel, Field

from app.service.catalog_client_service import catalog_client

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


@router.patch("/api/v1/systems/{system_id:path}/owner")
async def system_owner(
    system_id: str,
    payload: Annotated[SystemOwnerUpdate, Body()],
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
