from __future__ import annotations

import json
import logging
from pathlib import Path

from sqlalchemy import delete, func, select

from app.config.settings import Settings
from app.db.models import EdgeRow, GalaxyMetaRow, PolityRow, SearchEntryRow, SessionLocal, SystemRow

logger = logging.getLogger(__name__)


class CatalogSeedService:
    """Syncs systems/*.json (+ galaxy-index) into Postgres on every startup."""

    def __init__(self, settings: Settings):
        self.settings = settings

    def system_count(self) -> int:
        with SessionLocal() as session:
            return int(session.scalar(select(func.count()).select_from(SystemRow)) or 0)

    def sync_on_startup(self) -> dict:
        """Refresh index tables and upsert every system JSON (background-friendly)."""
        return self.sync(full=True)

    def seed_if_empty(self, *, force: bool = False) -> dict:
        return self.sync(wipe_first=force, full=True)

    def _system_row(
        self,
        *,
        system_id: str,
        detail: dict,
        index_row: dict,
        shard: str,
    ) -> SystemRow:
        return SystemRow(
            id=system_id,
            token=detail.get("token") or index_row.get("token") or "",
            stem=detail.get("stem") if detail.get("stem") is not None else index_row.get("stem"),
            kind=detail.get("kind") or index_row.get("kind") or "star",
            name_en=detail.get("nameEn") or index_row.get("nameEn") or "",
            name_ru=detail.get("nameRu") or index_row.get("nameRu") or "",
            star_type_key=detail.get("starTypeKey") or index_row.get("starTypeKey") or "",
            sector_id=detail.get("sectorId") or index_row.get("sectorId") or "",
            capital=bool(detail.get("capital", index_row.get("capital", False))),
            x=float(detail.get("x", index_row.get("x", 0.0)) or 0.0),
            y=float(detail.get("y", index_row.get("y", 0.0)) or 0.0),
            z=float(detail.get("z", index_row.get("z", 0.0)) or 0.0),
            world_count=int(index_row.get("worldCount") or len(detail.get("worlds") or []) or 0),
            shard=shard,
            detail=detail,
        )

    def sync(self, *, wipe_first: bool = False, full: bool = False) -> dict:
        index_path = Path(self.settings.galaxy_index_path)
        systems_dir = Path(self.settings.systems_dir)
        if not index_path.is_file():
            raise FileNotFoundError(f"Galaxy index not found: {index_path}")
        if not systems_dir.is_dir():
            raise FileNotFoundError(f"Systems dir not found: {systems_dir}")

        index = json.loads(index_path.read_text(encoding="utf-8"))
        index_by_id = {row["id"]: row for row in (index.get("systems") or []) if row.get("id")}
        index_by_shard = {
            row.get("shard"): row for row in (index.get("systems") or []) if row.get("shard")
        }

        json_files = sorted(systems_dir.glob("*.json"))
        if not json_files:
            raise RuntimeError(f"No system JSON files in {systems_dir}")

        before = self.system_count()
        seen_system_ids: set[str] = set()
        seen_polity_stems: set[str] = set()
        upserted = 0
        removed = 0
        skipped = 0

        with SessionLocal() as session:
            if wipe_first:
                session.execute(delete(SearchEntryRow))
                session.execute(delete(EdgeRow))
                session.execute(delete(PolityRow))
                session.execute(delete(SystemRow))
                session.execute(delete(GalaxyMetaRow))
                session.commit()
                full = True

            session.merge(GalaxyMetaRow(id=1, payload=index.get("meta") or {}))

            for polity in index.get("polities") or []:
                stem = polity.get("stem")
                if not stem:
                    continue
                seen_polity_stems.add(stem)
                session.merge(PolityRow(stem=stem, payload=polity))

            session.execute(delete(EdgeRow))
            for edge in index.get("edgesCanon") or []:
                a, b = edge.get("a"), edge.get("b")
                if a and b:
                    session.add(EdgeRow(a=a, b=b, graph="canon"))
            for edge in index.get("edgesDisplay") or []:
                a, b = edge.get("a"), edge.get("b")
                if a and b:
                    session.add(EdgeRow(a=a, b=b, graph="display"))

            session.execute(delete(SearchEntryRow))
            for entry in index.get("search") or []:
                key = str(entry.get("id") or "")
                if not key:
                    continue
                entry_key = f"{entry.get('kind', 'unknown')}:{key}:{entry.get('token', '')}"
                session.add(SearchEntryRow(entry_key=entry_key, payload=entry))

            session.commit()

            existing_ids = set(session.scalars(select(SystemRow.id)).all())
            batch: list[SystemRow] = []

            for path in json_files:
                detail = json.loads(path.read_text(encoding="utf-8"))
                shard = f"systems/{path.name}"
                system_id = detail.get("id") or index_by_shard.get(shard, {}).get("id")
                if not system_id:
                    logger.warning("Skip system JSON without id: %s", path.name)
                    continue

                seen_system_ids.add(system_id)
                if not full and system_id in existing_ids:
                    skipped += 1
                    continue

                index_row = index_by_id.get(system_id) or index_by_shard.get(shard) or {}
                batch.append(
                    self._system_row(
                        system_id=system_id,
                        detail=detail,
                        index_row=index_row,
                        shard=shard,
                    )
                )
                upserted += 1
                if len(batch) >= 200:
                    for row in batch:
                        session.merge(row)
                    session.commit()
                    batch.clear()
                    logger.info("Catalog sync progress: %s upserted / %s files", upserted, len(json_files))

            for row in batch:
                session.merge(row)
            if batch:
                session.commit()

            stale_ids = existing_ids - seen_system_ids
            # After upserts, also drop ids that disappeared from JSON.
            current_ids = set(session.scalars(select(SystemRow.id)).all())
            stale_ids = current_ids - seen_system_ids
            if stale_ids:
                removed = len(stale_ids)
                session.execute(delete(SystemRow).where(SystemRow.id.in_(stale_ids)))
                session.commit()
                logger.info("Removed %s stale systems from DB", removed)

            existing_stems = set(session.scalars(select(PolityRow.stem)).all())
            stale_stems = existing_stems - seen_polity_stems
            if stale_stems:
                session.execute(delete(PolityRow).where(PolityRow.stem.in_(stale_stems)))
                session.commit()

        after = self.system_count()
        result = {
            "synced": True,
            "systemsBefore": before,
            "systemsAfter": after,
            "upserted": upserted,
            "skippedExisting": skipped,
            "jsonFiles": len(json_files),
            "removed": removed,
            "wipeFirst": wipe_first,
            "full": full,
        }
        logger.info(
            "Catalog sync complete: %s systems (was %s), upserted %s, skipped %s, removed %s",
            after,
            before,
            upserted,
            skipped,
            removed,
        )
        return result
