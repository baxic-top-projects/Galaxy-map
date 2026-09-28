from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.config.settings import settings
from app.controller.catalog_controller import router as catalog_router
from app.controller.health_controller import router as health_router
from app.db.models import init_db
from app.service.catalog_seed_service import CatalogSeedService

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(_app: FastAPI):
    init_db()
    if settings.seed_on_startup:
        try:
            CatalogSeedService(settings).seed_if_empty()
        except Exception:
            logger.exception("Catalog seed failed")
    yield


app = FastAPI(title="Galaxy Catalog Service", version="1.0.0", lifespan=lifespan)
app.include_router(health_router)
app.include_router(catalog_router)
