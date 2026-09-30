from __future__ import annotations

import logging
import threading
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.api import router
from app.db import init_db

logger = logging.getLogger(__name__)
_db_status: dict[str, str | None] = {"status": "pending", "error": None}
_status_lock = threading.Lock()


def _initialize_database() -> None:
    with _status_lock:
        _db_status["status"] = "running"
    try:
        init_db()
    except Exception as exc:  # health remains available when Postgres is unavailable
        logger.exception("Auth database initialization failed")
        with _status_lock:
            _db_status.update(status="failed", error=type(exc).__name__)
    else:
        with _status_lock:
            _db_status.update(status="ready", error=None)


@asynccontextmanager
async def lifespan(_app: FastAPI):
    threading.Thread(target=_initialize_database, name="auth-db-init", daemon=True).start()
    yield


app = FastAPI(title="Galaxy Auth Service", version="1.0.0", lifespan=lifespan)
app.include_router(router)


@app.get("/health", tags=["health"])
def health():
    with _status_lock:
        db = dict(_db_status)
    return {
        "status": "ok" if db["status"] in {"pending", "running", "ready"} else "degraded",
        "service": "auth-service",
        "database": db,
    }
