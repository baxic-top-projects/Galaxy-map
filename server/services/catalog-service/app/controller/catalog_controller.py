from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Body, Header, HTTPException

from app.config.settings import settings

from app.service.catalog_query_service import SystemOwnerUpdate, catalog_query

router = APIRouter()


@router.get("/internal/v1/galaxy")
def get_galaxy():
    return catalog_query.get_galaxy_index()


@router.get("/internal/v1/galaxy/graph")
def get_galaxy_graph():
    return catalog_query.get_galaxy_graph()


@router.patch("/internal/v1/systems/{system_id:path}/owner")
def patch_system_owner(
    system_id: str,
    payload: Annotated[SystemOwnerUpdate, Body()],
    x_internal_service_token: Annotated[str | None, Header()] = None,
):
    if (
        settings.internal_service_token
        and x_internal_service_token != settings.internal_service_token
    ):
        raise HTTPException(status_code=403, detail="Invalid internal service token")
    return catalog_query.update_system_owner(system_id, payload.stem.strip())


@router.get("/internal/v1/systems/{system_id:path}")
def get_system(system_id: str):
    if system_id.startswith("systems/") or system_id.endswith(".json"):
        return catalog_query.get_system_by_shard(system_id)
    try:
        return catalog_query.get_system_by_id(system_id)
    except HTTPException as exc:
        if exc.status_code != 404:
            raise
        return catalog_query.get_system_by_shard(system_id)
