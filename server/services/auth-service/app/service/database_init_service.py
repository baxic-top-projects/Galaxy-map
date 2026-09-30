from __future__ import annotations

import logging
import threading

from app.db import init_db

logger = logging.getLogger(__name__)
_status: dict[str, str | None] = {"status": "pending", "error": None}
_status_lock = threading.Lock()


def initialize_database() -> None:
    with _status_lock:
        _status["status"] = "running"
    try:
        init_db()
    except Exception as exc:
        logger.exception("Auth database initialization failed")
        with _status_lock:
            _status.update(status="failed", error=type(exc).__name__)
    else:
        with _status_lock:
            _status.update(status="ready", error=None)


def run_in_background() -> None:
    threading.Thread(
        target=initialize_database,
        name="auth-db-init",
        daemon=True,
    ).start()


def database_status() -> dict[str, str | None]:
    with _status_lock:
        return dict(_status)
