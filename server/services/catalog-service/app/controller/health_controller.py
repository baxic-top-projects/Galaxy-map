from __future__ import annotations

from fastapi import APIRouter

from app.service.catalog_query_service import catalog_query
from app.service.catalog_sync_runner import sync_status

router = APIRouter()


@router.get("/health")
def health():
    sync = sync_status()
    # Don't touch the DB until background init/sync settles: a slow or unreachable
    # Postgres would otherwise block this endpoint past the container healthcheck timeout.
    if sync.get("status") in ("running", "failed"):
        return {
            "status": "ok" if sync["status"] == "running" else "degraded",
            "service": "catalog-service",
            "hasSystems": None,
            "db": "pending" if sync["status"] == "running" else "error",
            "sync": sync,
        }
    payload = catalog_query.health()
    payload["sync"] = sync
    return payload
