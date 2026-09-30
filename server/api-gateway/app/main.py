from __future__ import annotations

from fastapi import FastAPI

from app.config.cors_config import apply_cors
from app.controller.auth_controller import router as auth_router
from app.controller.asset_controller import router as asset_router
from app.controller.catalog_controller import router as catalog_router
from app.controller.health_controller import router as health_router
from app.controller.storm_controller import router as storm_router

app = FastAPI(title="Galaxy Map API Gateway", version="1.0.0")
apply_cors(app)
app.include_router(health_router)
app.include_router(auth_router)
app.include_router(storm_router)
app.include_router(asset_router)
app.include_router(catalog_router)
