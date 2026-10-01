"""Freeze the current frontier polity layout for stable future ownership."""

from __future__ import annotations

import json
import math
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CATALOG_SERVICE = ROOT / "server" / "services" / "catalog-service"
OUTPUT = (
    CATALOG_SERVICE
    / "app"
    / "data"
    / "frontier_layout_lock.json"
)

sys.path.insert(0, str(CATALOG_SERVICE))

from app.service.frontier_polities import (  # noqa: E402
    LOCKED_FRONTIER_POLITIES,
    allocate_frontier_polities,
    assign_objects_inside_territories,
)
from app.service.spiral_geometry import generate_arm_objects  # noqa: E402


def main() -> int:
    objects = generate_arm_objects()
    base_ownership, clusters = allocate_frontier_polities(objects)
    ownership = dict(base_ownership)
    additions = assign_objects_inside_territories(objects, ownership, [])
    ownership.update(additions)
    by_id = {obj.id: obj for obj in objects}
    outer_floor = {
        stem: sum(
            math.hypot(obj.x, obj.y)
            for obj in cluster
            if obj.kind == "star"
        )
        / sum(obj.kind == "star" for obj in cluster)
        for stem, cluster in clusters.items()
    }
    outer_candidates = assign_objects_inside_territories(
        objects,
        ownership,
        [],
    )
    additions.update(
        {
            object_id: stem
            for object_id, stem in outer_candidates.items()
            if stem in outer_floor
            and math.hypot(by_id[object_id].x, by_id[object_id].y)
            >= outer_floor[stem]
        }
    )
    ownership.update(additions)

    payload = {
        "version": 1,
        "polities": [
            polity.stem for polity in LOCKED_FRONTIER_POLITIES
        ],
        "baseOwnership": dict(sorted(base_ownership.items())),
        "ownership": dict(sorted(ownership.items())),
        "clusters": {
            stem: [obj.id for obj in cluster]
            for stem, cluster in sorted(clusters.items())
        },
        "coordinates": {
            object_id: [by_id[object_id].x, by_id[object_id].y, by_id[object_id].z]
            for object_id in sorted(ownership)
        },
    }
    OUTPUT.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(
        f"Wrote {OUTPUT} with {len(base_ownership)} base and "
        f"{len(ownership)} total assignments"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
