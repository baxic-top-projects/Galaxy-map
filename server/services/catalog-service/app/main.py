from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.config.settings import settings
from app.controller.catalog_controller import router as catalog_router
from app.controller.health_controller import router as health_router
from app.db.models import init_db
from app.service.catalog_sync_runner import run_sync_in_background

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(_app: FastAPI):
    init_db()
    if settings.seed_on_startup:
        run_sync_in_background(settings)
        logger.info("Catalog sync started in background")
    yield


app = FastAPI(title="Galaxy Catalog Service", version="1.0.0", lifespan=lifespan)
app.include_router(health_router)
app.include_router(catalog_router)
