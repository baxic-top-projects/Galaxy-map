from __future__ import annotations

from fastapi import APIRouter

from app.service.s3_asset_service import asset_service

router = APIRouter()


@router.get("/health")
def health():
    return asset_service.health()
