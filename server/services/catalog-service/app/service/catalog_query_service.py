from __future__ import annotations

import json
from pathlib import Path

from fastapi import HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.exc import ProgrammingError, OperationalError

from app.config.settings import settings
from app.db.models import (
    EdgeRow,
    GalaxyMetaRow,
    PolityRow,
    SearchEntryRow,
    SessionLocal,
    SystemOwnerOverrideRow,
    SystemRow,
)
from app.service.catalog_cache_service import CatalogCacheService, catalog_cache
from app.service.frontier_naming import (
    generated_frontier_worlds,
    natural_frontier_star_name,
)

_OWNERSHIP_PATH = Path(__file__).resolve().parents[1] / "data" / "visual_ownership.json"


def _load_visual_ownership() -> dict[str, str]:
    if not _OWNERSHIP_PATH.is_file():
        return {}
    return json.loads(_OWNERSHIP_PATH.read_text(encoding="utf-8"))


VISUAL_OWNERSHIP = _load_visual_ownership()


class SystemOwnerUpdate(BaseModel):
    stem: str = Field(min_length=1, max_length=255)


def _manual_overrides(session) -> dict[str, str]:
    try:
        return {
            row.system_id: row.stem
            for row in session.scalars(select(SystemOwnerOverrideRow))
        }
    except (ProgrammingError, OperationalError):
        # Table is created on catalog startup via init_db; fail open until then.
        session.rollback()
        return {}


def _apply_system_ownership(
    payload: dict,
    *,
    manual: dict[str, str] | None = None,
) -> dict:
    system_id = str(payload.get("id") or "")
    if not system_id:
        return payload

    visual_stem = VISUAL_OWNERSHIP.get(system_id)
    manual_stem = (manual or {}).get(system_id)
    next_stem = manual_stem or visual_stem
    if not next_stem or next_stem == payload.get("stem"):
        if manual_stem or visual_stem:
            # Preserve canonicalStem when the painted/manual stem already matches.
            if "canonicalStem" not in payload and payload.get("stem"):
                return payload
        return payload

    canonical = payload.get("canonicalStem", payload.get("stem"))
    return {**payload, "canonicalStem": canonical, "stem": next_stem}


def _apply_galaxy_ownership(payload: dict, *, manual: dict[str, str] | None = None) -> dict:
    next_payload = {**payload}
    if "systems" in payload:
        next_payload["systems"] = [
            _apply_system_ownership(system, manual=manual)
            for system in payload.get("systems") or []
        ]
    if "search" in payload:
        next_payload["search"] = [
            _apply_system_ownership(entry, manual=manual)
            for entry in payload.get("search") or []
        ]
    return next_payload


def _system_index_row(row: SystemRow) -> dict:
    return {
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
        "territoryAnchor": (row.detail or {}).get("territoryAnchor", True),
        "shard": row.shard,
    }


UNOWNED_SYSTEM_CHUNK = "__unowned__"


def _system_chunk_key(system: dict) -> str:
    stem = system.get("stem")
    return stem if stem else UNOWNED_SYSTEM_CHUNK


def _is_seed_system(system: dict) -> bool:
    """Structural markers shown before polity chunks finish hydrating."""
    kind = system.get("kind")
    return kind in {"well", "junction"} or bool(system.get("capital"))


def _group_systems_by_chunk(systems: list[dict]) -> dict[str, list[dict]]:
    grouped: dict[str, list[dict]] = {}
    for system in systems:
        key = _system_chunk_key(system)
        grouped.setdefault(key, []).append(system)
    return grouped


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

    def _cache_system_chunks(
        self,
        systems: list[dict],
        *,
        cache_generation: int,
    ) -> list[str]:
        ttl = settings.redis_galaxy_ttl_seconds
        grouped = _group_systems_by_chunk(systems)
        chunk_keys = sorted(grouped)
        for stem, chunk_systems in grouped.items():
            self.cache.set_json(
                f"galaxy:systems:{stem}",
                {"stem": stem, "systems": chunk_systems},
                ttl,
                expected_generation=cache_generation,
            )
        self.cache.set_json(
            "galaxy:systemChunks",
            {"chunks": chunk_keys},
            ttl,
            expected_generation=cache_generation,
        )
        return chunk_keys

    def _cache_galaxy_slices(self, result: dict, *, cache_generation: int) -> None:
        ttl = settings.redis_galaxy_ttl_seconds
        systems = result.get("systems") or []
        seed_systems = [system for system in systems if _is_seed_system(system)]
        chunk_keys = self._cache_system_chunks(systems, cache_generation=cache_generation)
        self.cache.set_json("galaxy", result, ttl, expected_generation=cache_generation)
        self.cache.set_json(
            "galaxy:map",
            {
                "meta": result.get("meta") or {},
                "polities": result.get("polities") or [],
                "systems": seed_systems,
                "systemChunks": chunk_keys,
            },
            ttl,
            expected_generation=cache_generation,
        )
        # Keep a full systems list for callers that still want one map payload.
        self.cache.set_json(
            "galaxy:map:full",
            {
                "meta": result.get("meta") or {},
                "polities": result.get("polities") or [],
                "systems": systems,
            },
            ttl,
            expected_generation=cache_generation,
        )
        self.cache.set_json(
            "galaxy:edges",
            {
                "edgesCanon": result.get("edgesCanon") or [],
                "edgesDisplay": result.get("edgesDisplay") or [],
            },
            ttl,
            expected_generation=cache_generation,
        )
        self.cache.set_json(
            "galaxy:search",
            {"search": result.get("search") or []},
            ttl,
            expected_generation=cache_generation,
        )

    def _build_galaxy_index(self, session) -> dict:
        meta = session.get(GalaxyMetaRow, 1)
        polities = [
            row.payload for row in session.scalars(select(PolityRow).order_by(PolityRow.stem))
        ]
        systems = [
            _system_index_row(row)
            for row in session.scalars(select(SystemRow).order_by(SystemRow.id))
        ]
        edges_canon = [
            {"a": row.a, "b": row.b}
            for row in session.scalars(select(EdgeRow).where(EdgeRow.graph == "canon"))
        ]
        edges_display = [
            {"a": row.a, "b": row.b}
            for row in session.scalars(select(EdgeRow).where(EdgeRow.graph == "display"))
        ]
        search = [
            row.payload
            for row in session.scalars(select(SearchEntryRow).order_by(SearchEntryRow.id))
        ]
        return {
            "meta": meta.payload if meta else {},
            "polities": polities,
            "systems": systems,
            "edgesCanon": edges_canon,
            "edgesDisplay": edges_display,
            "search": search,
        }

    def get_galaxy_index(self) -> dict:
        with SessionLocal() as session:
            cache_generation = self.cache.generation
            manual = _manual_overrides(session)
            cached = self.cache.get_json("galaxy")
            if cached is not None:
                return _apply_galaxy_ownership(cached, manual=manual)

            result = self._build_galaxy_index(session)
            # Cache the catalog without overlays so manual ownership stays live.
            self._cache_galaxy_slices(result, cache_generation=cache_generation)
            return _apply_galaxy_ownership(result, manual=manual)

    def get_galaxy_map(self) -> dict:
        """Bootstrap: meta, polities, seed systems, and polity chunk ids."""
        with SessionLocal() as session:
            cache_generation = self.cache.generation
            manual = _manual_overrides(session)
            cached = self.cache.get_json("galaxy:map")
            if cached is None:
                full = self.cache.get_json("galaxy")
                if full is not None:
                    owned = _apply_galaxy_ownership(
                        {
                            "meta": full.get("meta") or {},
                            "polities": full.get("polities") or [],
                            "systems": full.get("systems") or [],
                        },
                        manual=manual,
                    )
                    systems = owned.get("systems") or []
                    chunk_keys = self._cache_system_chunks(
                        systems,
                        cache_generation=cache_generation,
                    )
                    cached = {
                        "meta": owned.get("meta") or {},
                        "polities": owned.get("polities") or [],
                        "systems": [system for system in systems if _is_seed_system(system)],
                        "systemChunks": chunk_keys,
                    }
                    self.cache.set_json(
                        "galaxy:map",
                        cached,
                        settings.redis_galaxy_ttl_seconds,
                        expected_generation=cache_generation,
                    )
                    return cached
            if cached is not None:
                # Seed/chunk payloads are cached after ownership is applied.
                if "systemChunks" in cached:
                    return cached
                owned = _apply_galaxy_ownership(cached, manual=manual)
                systems = owned.get("systems") or []
                chunk_keys = self._cache_system_chunks(
                    systems,
                    cache_generation=cache_generation,
                )
                result = {
                    "meta": owned.get("meta") or {},
                    "polities": owned.get("polities") or [],
                    "systems": [system for system in systems if _is_seed_system(system)],
                    "systemChunks": chunk_keys,
                }
                self.cache.set_json(
                    "galaxy:map",
                    result,
                    settings.redis_galaxy_ttl_seconds,
                    expected_generation=cache_generation,
                )
                return result

            meta = session.get(GalaxyMetaRow, 1)
            polities = [
                row.payload
                for row in session.scalars(select(PolityRow).order_by(PolityRow.stem))
            ]
            systems = [
                _system_index_row(row)
                for row in session.scalars(select(SystemRow).order_by(SystemRow.id))
            ]
            owned = _apply_galaxy_ownership(
                {
                    "meta": meta.payload if meta else {},
                    "polities": polities,
                    "systems": systems,
                },
                manual=manual,
            )
            owned_systems = owned.get("systems") or []
            chunk_keys = self._cache_system_chunks(
                owned_systems,
                cache_generation=cache_generation,
            )
            result = {
                "meta": owned.get("meta") or {},
                "polities": owned.get("polities") or [],
                "systems": [system for system in owned_systems if _is_seed_system(system)],
                "systemChunks": chunk_keys,
            }
            self.cache.set_json(
                "galaxy:map",
                result,
                settings.redis_galaxy_ttl_seconds,
                expected_generation=cache_generation,
            )
            return result

    def get_galaxy_systems_chunk(self, stem: str) -> dict:
        """Systems for one polity stem (or __unowned__)."""
        key = stem.strip() if stem and stem.strip() else UNOWNED_SYSTEM_CHUNK
        if key == "unowned":
            key = UNOWNED_SYSTEM_CHUNK
        with SessionLocal() as session:
            cache_generation = self.cache.generation
            manual = _manual_overrides(session)
            cached = self.cache.get_json(f"galaxy:systems:{key}")
            if cached is not None:
                return cached

            full = self.cache.get_json("galaxy") or self.cache.get_json("galaxy:map:full")
            if full is not None:
                owned = _apply_galaxy_ownership(full, manual=manual)
                systems = owned.get("systems") or []
                self._cache_system_chunks(systems, cache_generation=cache_generation)
                cached = self.cache.get_json(f"galaxy:systems:{key}")
                if cached is not None:
                    return cached
                return {"stem": key, "systems": []}

            systems = [
                _system_index_row(row)
                for row in session.scalars(select(SystemRow).order_by(SystemRow.id))
            ]
            owned = _apply_galaxy_ownership({"systems": systems}, manual=manual)
            owned_systems = owned.get("systems") or []
            self._cache_system_chunks(owned_systems, cache_generation=cache_generation)
            cached = self.cache.get_json(f"galaxy:systems:{key}")
            if cached is not None:
                return cached
            return {"stem": key, "systems": []}

    def get_galaxy_edges(self) -> dict:
        with SessionLocal() as session:
            cache_generation = self.cache.generation
            cached = self.cache.get_json("galaxy:edges")
            if cached is None:
                full = self.cache.get_json("galaxy")
                if full is not None:
                    cached = {
                        "edgesCanon": full.get("edgesCanon") or [],
                        "edgesDisplay": full.get("edgesDisplay") or [],
                    }
            if cached is not None:
                return cached

            result = {
                "edgesCanon": [
                    {"a": row.a, "b": row.b}
                    for row in session.scalars(select(EdgeRow).where(EdgeRow.graph == "canon"))
                ],
                "edgesDisplay": [
                    {"a": row.a, "b": row.b}
                    for row in session.scalars(select(EdgeRow).where(EdgeRow.graph == "display"))
                ],
            }
            self.cache.set_json(
                "galaxy:edges",
                result,
                settings.redis_galaxy_ttl_seconds,
                expected_generation=cache_generation,
            )
            return result

    def get_galaxy_search(self) -> dict:
        with SessionLocal() as session:
            cache_generation = self.cache.generation
            manual = _manual_overrides(session)
            cached = self.cache.get_json("galaxy:search")
            if cached is None:
                full = self.cache.get_json("galaxy")
                if full is not None:
                    cached = {"search": full.get("search") or []}
            if cached is not None:
                return _apply_galaxy_ownership(cached, manual=manual)

            result = {
                "search": [
                    row.payload
                    for row in session.scalars(
                        select(SearchEntryRow).order_by(SearchEntryRow.id)
                    )
                ]
            }
            self.cache.set_json(
                "galaxy:search",
                result,
                settings.redis_galaxy_ttl_seconds,
                expected_generation=cache_generation,
            )
            return _apply_galaxy_ownership(result, manual=manual)

    def get_galaxy_graph(self) -> dict:
        """Lean id/kind + edge payload for storm-service (avoids the full index in memory)."""
        with SessionLocal() as session:
            systems = [
                {"id": system_id, "kind": kind}
                for system_id, kind in session.execute(
                    select(SystemRow.id, SystemRow.kind).order_by(SystemRow.id)
                )
            ]
            edges: dict[str, list[dict]] = {"canon": [], "display": []}
            for a, b, graph in session.execute(select(EdgeRow.a, EdgeRow.b, EdgeRow.graph)):
                if graph in edges:
                    edges[graph].append({"a": a, "b": b})
            return {
                "systems": systems,
                "edgesCanon": edges["canon"],
                "edgesDisplay": edges["display"],
            }

    def get_system_by_id(self, system_id: str) -> dict:
        key = f"system:id:{system_id}"
        with SessionLocal() as session:
            cache_generation = self.cache.generation
            manual = _manual_overrides(session)
            cached = self.cache.get_json(key)
            if cached is not None:
                return _apply_system_ownership(cached, manual=manual)
            row = session.get(SystemRow, system_id)
            if row is None:
                raise HTTPException(status_code=404, detail="System not found")
            self.cache.set_json(
                key,
                row.detail,
                settings.redis_system_ttl_seconds,
                expected_generation=cache_generation,
            )
            return _apply_system_ownership(row.detail, manual=manual)

    def get_system_by_shard(self, shard: str) -> dict:
        normalized = shard.lstrip("/")
        if not normalized.startswith("systems/"):
            normalized = f"systems/{normalized}"
        key = f"system:shard:{normalized}"
        with SessionLocal() as session:
            cache_generation = self.cache.generation
            manual = _manual_overrides(session)
            cached = self.cache.get_json(key)
            if cached is not None:
                return _apply_system_ownership(cached, manual=manual)
            row = session.scalar(select(SystemRow).where(SystemRow.shard == normalized))
            if row is None:
                # try bare filename
                bare = normalized.split("/", 1)[-1]
                row = session.scalar(select(SystemRow).where(SystemRow.shard.endswith(bare)))
            if row is None:
                raise HTTPException(status_code=404, detail="System shard not found")
            self.cache.set_json(
                key,
                row.detail,
                settings.redis_system_ttl_seconds,
                expected_generation=cache_generation,
            )
            return _apply_system_ownership(row.detail, manual=manual)

    def update_system_owner(self, system_id: str, stem: str) -> dict:
        with SessionLocal() as session:
            row = session.get(SystemRow, system_id)
            if row is None:
                raise HTTPException(status_code=404, detail="System not found")
            if row.kind == "well":
                raise HTTPException(
                    status_code=400,
                    detail="Axis Well ownership is fixed as neutral",
                )
            polity = session.get(PolityRow, stem)
            if polity is None:
                raise HTTPException(status_code=400, detail=f"Unknown polity: {stem}")

            override = session.get(SystemOwnerOverrideRow, system_id)
            if override is None:
                session.add(SystemOwnerOverrideRow(system_id=system_id, stem=stem))
            else:
                override.stem = stem

            detail = dict(row.detail or {})
            is_unnamed_star = row.kind == "star" and not (
                detail.get("token")
                or detail.get("nameEn")
                or detail.get("nameRu")
                or getattr(row, "token", "")
                or getattr(row, "name_en", "")
                or getattr(row, "name_ru", "")
            )
            if is_unnamed_star:
                token, name_en, name_ru = natural_frontier_star_name(row.id)
                worlds = generated_frontier_worlds(row.id, token)
                detail.update(
                    {
                        "token": token,
                        "nameEn": name_en,
                        "nameRu": name_ru,
                        "worlds": worlds,
                        "worldCount": len(worlds),
                    }
                )
                row.token = token
                row.name_en = name_en
                row.name_ru = name_ru
                row.world_count = len(worlds)
                row.detail = detail
                session.add(
                    SearchEntryRow(
                        entry_key=f"system:{row.id}:{token}",
                        payload={
                            "id": row.id,
                            "kind": "system",
                            "token": token,
                            "nameEn": name_en,
                            "nameRu": name_ru,
                            "stem": stem,
                        },
                    )
                )
                for world in worlds:
                    session.add(
                        SearchEntryRow(
                            entry_key=f"world:{row.id}:{world['token']}",
                            payload={
                                "id": row.id,
                                "kind": "world",
                                "token": world["token"],
                                "nameEn": world["nameEn"],
                                "nameRu": world["nameRu"],
                                "stem": stem,
                                "planetTypeKey": world["planetTypeKey"],
                            },
                        )
                    )
            session.commit()

            self.cache.clear()
            detail["id"] = row.id
            detail["stem"] = stem
            detail["canonicalStem"] = row.stem
            return detail


catalog_query = CatalogQueryService()
