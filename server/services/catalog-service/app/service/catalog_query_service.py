from __future__ import annotations

from fastapi import HTTPException
from sqlalchemy import select

from app.db.models import EdgeRow, GalaxyMetaRow, PolityRow, SearchEntryRow, SessionLocal, SystemRow


class CatalogQueryService:
    """Read galaxy catalog from Postgres."""

    def health(self) -> dict:
        with SessionLocal() as session:
            systems = session.scalar(select(SystemRow.id).limit(1))
            return {
                "status": "ok" if systems is not None else "empty",
                "service": "catalog-service",
                "hasSystems": systems is not None,
            }

    def get_galaxy_index(self) -> dict:
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
            return {
                "meta": meta.payload if meta else {},
                "polities": polities,
                "systems": systems,
                "edgesCanon": edges_canon,
                "edgesDisplay": edges_display,
                "search": search,
            }

    def get_system_by_id(self, system_id: str) -> dict:
        with SessionLocal() as session:
            row = session.get(SystemRow, system_id)
            if row is None:
                raise HTTPException(status_code=404, detail="System not found")
            return row.detail

    def get_system_by_shard(self, shard: str) -> dict:
        normalized = shard.lstrip("/")
        if not normalized.startswith("systems/"):
            normalized = f"systems/{normalized}"
        with SessionLocal() as session:
            row = session.scalar(select(SystemRow).where(SystemRow.shard == normalized))
            if row is None:
                # try bare filename
                bare = normalized.split("/", 1)[-1]
                row = session.scalar(select(SystemRow).where(SystemRow.shard.endswith(bare)))
            if row is None:
                raise HTTPException(status_code=404, detail="System shard not found")
            return row.detail


catalog_query = CatalogQueryService()
