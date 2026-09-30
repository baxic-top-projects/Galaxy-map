from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.controller.auth_controller import router as auth_router
from app.controller.health_controller import router as health_router
from app.service.database_init_service import run_in_background


@asynccontextmanager
async def lifespan(_app: FastAPI):
    run_in_background()
    yield


app = FastAPI(title="Galaxy Auth Service", version="1.0.0", lifespan=lifespan)
app.include_router(health_router)
app.include_router(auth_router)
