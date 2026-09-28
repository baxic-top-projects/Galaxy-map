from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from concurrent.futures import TimeoutError as FutureTimeoutError

from fastapi import APIRouter

from app.service.catalog_query_service import catalog_query
from app.service.catalog_sync_runner import sync_status

router = APIRouter()

# The container healthcheck times out after 5s; keep the DB probe well under that.
DB_PROBE_TIMEOUT_SECONDS = 2.0
_probe_executor = ThreadPoolExecutor(max_workers=2, thread_name_prefix="health-db-probe")


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
    future = _probe_executor.submit(catalog_query.health)
    try:
        payload = future.result(timeout=DB_PROBE_TIMEOUT_SECONDS)
    except FutureTimeoutError:
        payload = {
            "status": "degraded",
            "service": "catalog-service",
            "hasSystems": None,
            "db": "timeout",
        }
    payload["sync"] = sync
    return payload
