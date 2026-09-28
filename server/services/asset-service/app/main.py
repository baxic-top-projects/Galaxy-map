from __future__ import annotations

from fastapi import FastAPI

from app.controller.asset_controller import router as asset_router
from app.controller.health_controller import router as health_router

app = FastAPI(title="Galaxy Asset Service", version="1.0.0")
app.include_router(health_router)
app.include_router(asset_router)
