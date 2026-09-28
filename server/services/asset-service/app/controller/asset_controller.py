from __future__ import annotations

from fastapi import APIRouter, Query

from app.dto.asset import AssetKind, AssetManifestDto, AssetResolveDto
from app.service.s3_asset_service import asset_service

router = APIRouter()


@router.get("/internal/v1/assets/manifest", response_model=AssetManifestDto)
def get_manifest(force: bool = Query(False, description="Bypass in-memory cache")) -> AssetManifestDto:
    return asset_service.manifest(force=force)


@router.get("/internal/v1/assets/models/{kind}/{key}", response_model=AssetResolveDto)
def resolve_model(kind: AssetKind, key: str) -> AssetResolveDto:
    return asset_service.resolve(kind, key)
