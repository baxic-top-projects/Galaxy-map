from __future__ import annotations

from fastapi import APIRouter, HTTPException

from app.service.catalog_query_service import catalog_query

router = APIRouter()


@router.get("/internal/v1/galaxy")
def get_galaxy():
    return catalog_query.get_galaxy_index()


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
