from __future__ import annotations

import json
from pathlib import Path

from fastapi import HTTPException
from sqlalchemy import select

from app.config.settings import settings
from app.db.models import EdgeRow, GalaxyMetaRow, PolityRow, SearchEntryRow, SessionLocal, SystemRow
from app.service.catalog_cache_service import CatalogCacheService, catalog_cache

_OWNERSHIP_PATH = Path(__file__).resolve().parents[1] / "data" / "visual_ownership.json"


def _load_visual_ownership() -> dict[str, str]:
    if not _OWNERSHIP_PATH.is_file():
        return {}
    return json.loads(_OWNERSHIP_PATH.read_text(encoding="utf-8"))


VISUAL_OWNERSHIP = _load_visual_ownership()


def _apply_system_ownership(payload: dict) -> dict:
    stem = VISUAL_OWNERSHIP.get(str(payload.get("id") or ""))
    if not stem or stem == payload.get("stem"):
        return payload
    return {**payload, "canonicalStem": payload.get("stem"), "stem": stem}


def _apply_galaxy_ownership(payload: dict) -> dict:
    return {
        **payload,
        "systems": [
            _apply_system_ownership(system)
            for system in payload.get("systems") or []
        ],
        "search": [
            _apply_system_ownership(entry)
            for entry in payload.get("search") or []
        ],
    }


class CatalogQueryService:
    """Read galaxy catalog from Postgres."""

    def __init__(self, cache: CatalogCacheService | None = None):
        self.cache = cache or catalog_cache

    def health(self) -> dict:
        try:
            with SessionLocal() as session:
                systems = session.scalar(select(SystemRow.id).limit(1))
                return {
                    "status": "ok" if systems is not None else "empty",
                    "service": "catalog-service",
                    "hasSystems": systems is not None,
                    "db": "ok",
                    "redis": self.cache.status(),
                }
        except Exception as exc:  # noqa: BLE001
            return {
                "status": "error",
                "service": "catalog-service",
                "hasSystems": False,
                "db": "error",
                "redis": self.cache.status(),
                "error": str(exc),
            }

    def get_galaxy_index(self) -> dict:
        cached = self.cache.get_json("galaxy")
        if cached is not None:
            return _apply_galaxy_ownership(cached)
        with SessionLocal() as session:
            meta = session.get(GalaxyMetaRow, 1)
            polities = [row.payload for row in session.scalars(select(PolityRow).order_by(PolityRow.stem))]
            systems = []
            for row in session.scalars(select(SystemRow).order_by(SystemRow.id)):
                systems.append(
                    {
                        "id": row.id,
                        "token": row.token,
                        "stem": row.stem,
                        "kind": row.kind,
                        "nameEn": row.name_en,
                        "nameRu": row.name_ru,
                        "starTypeKey": row.star_type_key,
                        "sectorId": row.sector_id,
                        "capital": row.capital,
                        "x": row.x,
                        "y": row.y,
                        "z": row.z,
                        "worldCount": row.world_count,
                        "shard": row.shard,
                    }
                )
            edges_canon = [
                {"a": row.a, "b": row.b}
                for row in session.scalars(select(EdgeRow).where(EdgeRow.graph == "canon"))
            ]
            edges_display = [
                {"a": row.a, "b": row.b}
                for row in session.scalars(select(EdgeRow).where(EdgeRow.graph == "display"))
            ]
            search = [row.payload for row in session.scalars(select(SearchEntryRow).order_by(SearchEntryRow.id))]
            result = {
                "meta": meta.payload if meta else {},
                "polities": polities,
                "systems": systems,
                "edgesCanon": edges_canon,
                "edgesDisplay": edges_display,
                "search": search,
            }
            result = _apply_galaxy_ownership(result)
            self.cache.set_json("galaxy", result, settings.redis_galaxy_ttl_seconds)
            return result

    def get_system_by_id(self, system_id: str) -> dict:
        key = f"system:id:{system_id}"
        cached = self.cache.get_json(key)
        if cached is not None:
            return _apply_system_ownership(cached)
        with SessionLocal() as session:
            row = session.get(SystemRow, system_id)
            if row is None:
                raise HTTPException(status_code=404, detail="System not found")
            detail = _apply_system_ownership(row.detail)
            self.cache.set_json(key, detail, settings.redis_system_ttl_seconds)
            return detail

    def get_system_by_shard(self, shard: str) -> dict:
        normalized = shard.lstrip("/")
        if not normalized.startswith("systems/"):
            normalized = f"systems/{normalized}"
        key = f"system:shard:{normalized}"
        cached = self.cache.get_json(key)
        if cached is not None:
            return _apply_system_ownership(cached)
        with SessionLocal() as session:
            row = session.scalar(select(SystemRow).where(SystemRow.shard == normalized))
            if row is None:
                # try bare filename
                bare = normalized.split("/", 1)[-1]
                row = session.scalar(select(SystemRow).where(SystemRow.shard.endswith(bare)))
            if row is None:
                raise HTTPException(status_code=404, detail="System shard not found")
            detail = _apply_system_ownership(row.detail)
            self.cache.set_json(key, detail, settings.redis_system_ttl_seconds)
            return detail


catalog_query = CatalogQueryService()
