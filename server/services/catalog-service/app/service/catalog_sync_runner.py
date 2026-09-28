from __future__ import annotations

import logging
import threading
from typing import Any

from app.config.settings import Settings
from app.service.catalog_seed_service import CatalogSeedService

logger = logging.getLogger(__name__)

_lock = threading.Lock()
_state: dict[str, Any] = {
    "status": "idle",  # idle | running | ok | failed
    "result": None,
    "error": None,
}


def sync_status() -> dict[str, Any]:
    with _lock:
        return dict(_state)


def _set_state(**kwargs: Any) -> None:
    with _lock:
        _state.update(kwargs)


def run_sync_in_background(settings: Settings) -> None:
    """Start catalog sync without blocking the HTTP server."""
    with _lock:
        if _state["status"] == "running":
            logger.info("Catalog sync already running")
            return
        _state["status"] = "running"
        _state["error"] = None

    def worker() -> None:
        try:
            result = CatalogSeedService(settings).sync_on_startup()
            _set_state(status="ok", result=result, error=None)
            logger.info("Catalog sync result: %s", result)
        except Exception as exc:  # noqa: BLE001
            logger.exception("Catalog sync failed")
            _set_state(status="failed", result=None, error=str(exc))

    thread = threading.Thread(target=worker, name="catalog-sync", daemon=True)
    thread.start()
