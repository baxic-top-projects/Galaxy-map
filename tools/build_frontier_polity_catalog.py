"""Build runtime catalog data for new frontier polities from EfolsMiradinsPact."""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CATALOG_SERVICE = ROOT / "server" / "services" / "catalog-service"
OUTPUT = CATALOG_SERVICE / "app" / "data" / "frontier_polity_catalog.json"

sys.path.insert(0, str(ROOT / "tools"))
sys.path.insert(0, str(CATALOG_SERVICE))

import export_galaxy as export  # noqa: E402
from app.service.frontier_polities import (  # noqa: E402
    FRONTIER_POLITIES,
    NEW_FRONTIER_STEMS,
)


def main() -> int:
    stems = {polity.stem for polity in FRONTIER_POLITIES}
    rows = export.build_rows()
    systems, _edges = export.mapmod.load_catalog(rows)
    records: dict[str, list[dict]] = {stem: [] for stem in stems}

    for key, system in sorted(systems.items()):
        stem = system.get("stem")
        kind = system.get("kind")
        if stem not in stems or kind not in {"star", "black_hole", "junction"}:
            continue

        token = system["token"]
        card = export._parse_system_card(
            export._star_path(stem, token, kind),
            kind,
        )
        if kind == "junction":
            star_type_key = "junction"
            card["nameEn"] = f"{token} Junction"
            card["nameRu"] = f"Стык {token}"
            card["starType"] = "Empty hypercorridor node"
        else:
            star_type_key = export._type_key(
                card["starType"],
                export.STAR_TYPE_KEYS,
                "class_g" if kind == "star" else "black_hole",
            )

        worlds = [
            export._enrich_world(stem, dict(world))
            for world in card["worlds"]
        ]
        for world in worlds:
            recorded = world.pop("_satellitesRecorded", False)
            if not recorded:
                world["satellites"] = export._generated_satellites(
                    f"{key}:world:{world['token']}",
                    world["nameEn"],
                    world["nameRu"],
                    world["planetTypeKey"],
                )

        uninhabited = [dict(body) for body in card["uninhabited"]]
        for body in uninhabited:
            body["satellites"] = export._generated_satellites(
                f"{key}:uninhabited:{body['nameEn']}",
                body["nameEn"],
                body["nameRu"],
                body["planetTypeKey"],
            )

        records[stem].append(
            {
                "canonicalId": key,
                "token": token,
                "kind": kind,
                "nameEn": card["nameEn"] or token,
                "nameRu": card["nameRu"] or token,
                "starType": card["starType"],
                "starTypeKey": star_type_key,
                "sectorId": card["sectorId"],
                "sectorNameEn": card["sectorNameEn"],
                "worlds": worlds,
                "uninhabited": uninhabited,
                "features": card["features"],
            }
        )

    for stem, entries in records.items():
        entries.sort(key=lambda entry: (entry["kind"], entry["token"]))
        star_count = sum(entry["kind"] == "star" for entry in entries)
        if stem in NEW_FRONTIER_STEMS or star_count < 20:
            # Incomplete dossiers (newest wave or sparse locked polities) are
            # filled at runtime with generated pocket-star names and worlds.
            continue

    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(
        json.dumps(records, ensure_ascii=False, separators=(",", ":")),
        encoding="utf-8",
    )
    print(
        f"Wrote {OUTPUT} with "
        f"{sum(len(entries) for entries in records.values())} canonical objects"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
