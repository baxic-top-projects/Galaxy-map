from __future__ import annotations

import json
import logging
from pathlib import Path

from sqlalchemy import func, select

from app.config.settings import Settings
from app.db.models import EdgeRow, GalaxyMetaRow, PolityRow, SearchEntryRow, SessionLocal, SystemRow

logger = logging.getLogger(__name__)


class CatalogSeedService:
    """Loads galaxy-index.json + system shards into Postgres once."""

    def __init__(self, settings: Settings):
        self.settings = settings

    def system_count(self) -> int:
        with SessionLocal() as session:
            return int(session.scalar(select(func.count()).select_from(SystemRow)) or 0)

    def seed_if_empty(self) -> dict:
        count = self.system_count()
        if count > 0:
            logger.info("Catalog already seeded (%s systems)", count)
            return {"seeded": False, "systems": count}

        index_path = Path(self.settings.galaxy_index_path)
        systems_dir = Path(self.settings.systems_dir)
        if not index_path.is_file():
            raise FileNotFoundError(f"Galaxy index not found: {index_path}")
        if not systems_dir.is_dir():
            raise FileNotFoundError(f"Systems dir not found: {systems_dir}")

        index = json.loads(index_path.read_text(encoding="utf-8"))
        detail_by_shard: dict[str, dict] = {}
        for path in systems_dir.glob("*.json"):
            payload = json.loads(path.read_text(encoding="utf-8"))
            shard = f"systems/{path.name}"
            detail_by_shard[shard] = payload
            # also allow lookup by bare filename
            detail_by_shard[path.name] = payload

        with SessionLocal() as session:
            session.add(GalaxyMetaRow(id=1, payload=index.get("meta") or {}))

            for polity in index.get("polities") or []:
                stem = polity.get("stem")
                if not stem:
                    continue
                session.add(PolityRow(stem=stem, payload=polity))

            for edge in index.get("edgesCanon") or []:
                a, b = edge.get("a"), edge.get("b")
                if a and b:
                    session.add(EdgeRow(a=a, b=b, graph="canon"))
            for edge in index.get("edgesDisplay") or []:
                a, b = edge.get("a"), edge.get("b")
                if a and b:
                    session.add(EdgeRow(a=a, b=b, graph="display"))

            for entry in index.get("search") or []:
                key = str(entry.get("id") or "")
                if not key:
                    continue
                # search ids can collide across kinds; keep kind in unique key
                entry_key = f"{entry.get('kind', 'unknown')}:{key}:{entry.get('token', '')}"
                session.add(SearchEntryRow(entry_key=entry_key, payload=entry))

            systems = index.get("systems") or []
            for row in systems:
                system_id = row.get("id")
                if not system_id:
                    continue
                shard = row.get("shard") or ""
                detail = detail_by_shard.get(shard) or detail_by_shard.get(Path(shard).name) or {}
                session.add(
                    SystemRow(
                        id=system_id,
                        token=row.get("token") or "",
                        stem=row.get("stem"),
                        kind=row.get("kind") or "star",
                        name_en=row.get("nameEn") or "",
                        name_ru=row.get("nameRu") or "",
                        star_type_key=row.get("starTypeKey") or "",
                        sector_id=row.get("sectorId") or "",
                        capital=bool(row.get("capital")),
                        x=float(row.get("x") or 0.0),
                        y=float(row.get("y") or 0.0),
                        z=float(row.get("z") or 0.0),
                        world_count=int(row.get("worldCount") or 0),
                        shard=shard,
                        detail=detail or {
                            "id": system_id,
                            "token": row.get("token"),
                            "stem": row.get("stem"),
                            "kind": row.get("kind"),
                            "nameEn": row.get("nameEn"),
                            "nameRu": row.get("nameRu"),
                            "starTypeKey": row.get("starTypeKey"),
                            "x": row.get("x"),
                            "y": row.get("y"),
                            "z": row.get("z"),
                            "worlds": [],
                            "uninhabited": [],
                            "features": [],
                        },
                    )
                )

            session.commit()

        final_count = self.system_count()
        logger.info("Catalog seeded with %s systems", final_count)
        return {"seeded": True, "systems": final_count}
