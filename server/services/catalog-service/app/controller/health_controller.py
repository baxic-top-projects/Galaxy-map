from __future__ import annotations

from fastapi import APIRouter

from app.service.catalog_query_service import catalog_query

router = APIRouter()


@router.get("/health")
def health():
    return catalog_query.health()
