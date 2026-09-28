from __future__ import annotations

from fastapi import APIRouter

from app.service.catalog_query_service import catalog_query
from app.service.catalog_sync_runner import sync_status

router = APIRouter()


@router.get("/health")
def health():
    payload = catalog_query.health()
    payload["sync"] = sync_status()
    # Stay healthy while background sync runs if DB is reachable.
    if payload.get("status") == "empty" and payload["sync"].get("status") == "running":
        payload["status"] = "ok"
    return payload
