"""Freeze the current frontier polity layout for stable future ownership."""

from __future__ import annotations

import hashlib
import json
import sys
from dataclasses import replace
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parents[1]
CATALOG_SERVICE = ROOT / "server" / "services" / "catalog-service"
OUTPUT = (
    CATALOG_SERVICE
    / "app"
    / "data"
    / "frontier_layout_lock.json"
)
GALAXY_API = "https://galaxyapi.baxic.ru/api/v1/galaxy"

sys.path.insert(0, str(CATALOG_SERVICE))

from app.service.frontier_polities import (  # noqa: E402
    BATCH29_FRONTIER_POLITIES,
    LOCKED_FRONTIER_POLITIES,
    ORIGINAL_FRONTIER_POLITIES,
    PREVIOUS_FRONTIER_POLITIES,
    allocate_frontier_polities,
    allocate_new_frontier_polities,
)
from app.service.spiral_geometry import generate_arm_objects  # noqa: E402


def main() -> int:
    """Snapshot live ownership for every currently locked frontier polity."""
    objects = generate_arm_objects()
    object_indexes = {obj.id: index for index, obj in enumerate(objects)}

    prior_lock: dict = {}
    if OUTPUT.is_file():
        prior_lock = json.loads(OUTPUT.read_text(encoding="utf-8"))

    for object_id, coordinates in (prior_lock.get("coordinates") or {}).items():
        index = object_indexes.get(object_id)
        if index is None:
            continue
        objects[index] = replace(
            objects[index],
            x=float(coordinates[0]),
            y=float(coordinates[1]),
            z=float(coordinates[2]),
        )
    object_indexes = {obj.id: index for index, obj in enumerate(objects)}
    by_id = {obj.id: obj for obj in objects}

    original_stems = {polity.stem for polity in ORIGINAL_FRONTIER_POLITIES}
    previous_stems = {polity.stem for polity in PREVIOUS_FRONTIER_POLITIES}
    locked_49_stems = original_stems | previous_stems
    prior_polities = list(prior_lock.get("polities") or [])
    prior_clusters = prior_lock.get("clusters") or {}
    prior_base = prior_lock.get("baseOwnership") or {}
    prior_ownership = prior_lock.get("ownership") or {}

    if set(prior_polities) >= locked_49_stems and locked_49_stems <= set(
        prior_clusters
    ):
        original_base = {
            object_id: stem
            for object_id, stem in prior_base.items()
            if stem in original_stems
        }
        previous_base = {
            object_id: stem
            for object_id, stem in prior_base.items()
            if stem in previous_stems
        }
        original_clusters = {
            stem: tuple(by_id[object_id] for object_id in prior_clusters[stem])
            for stem in sorted(original_stems)
        }
        previous_clusters = {
            stem: tuple(by_id[object_id] for object_id in prior_clusters[stem])
            for stem in sorted(previous_stems)
        }
        reserved_49 = {
            object_id: stem
            for object_id, stem in prior_ownership.items()
            if stem in locked_49_stems
        }
        if not reserved_49:
            reserved_49 = {**original_base, **previous_base}
    else:
        original_base, original_clusters = allocate_frontier_polities(objects)
        previous_base, previous_clusters = allocate_new_frontier_polities(
            objects,
            original_base,
            original_base,
            polities=PREVIOUS_FRONTIER_POLITIES,
        )
        reserved_49 = {**original_base, **previous_base}

    batch29_base, batch29_clusters = allocate_new_frontier_polities(
        objects,
        set(reserved_49),
        reserved_49,
        polities=BATCH29_FRONTIER_POLITIES,
    )

    clusters = {
        **original_clusters,
        **previous_clusters,
        **batch29_clusters,
    }
    base_ownership = {
        **original_base,
        **previous_base,
        **batch29_base,
    }
    object_indexes = {obj.id: index for index, obj in enumerate(objects)}

    locked_stems = {polity.stem for polity in LOCKED_FRONTIER_POLITIES}
    expected = [polity.stem for polity in LOCKED_FRONTIER_POLITIES]
    if len(expected) != 77:
        raise RuntimeError(f"Expected 77 locked polities, got {len(expected)}")

    galaxy = requests.get(GALAXY_API, timeout=120).json()
    ownership: dict[str, str] = {}
    coordinates: dict[str, list[float]] = {}
    for system in galaxy.get("systems") or []:
        system_id = str(system.get("id") or "")
        stem = system.get("stem")
        if not system_id.startswith("frontier:") or stem not in locked_stems:
            continue
        ownership[system_id] = stem
        coordinates[system_id] = [
            float(system["x"]),
            float(system["y"]),
            float(system["z"]),
        ]
        index = object_indexes.get(system_id)
        if index is not None:
            objects[index] = replace(
                objects[index],
                x=float(system["x"]),
                y=float(system["y"]),
                z=float(system["z"]),
            )

    for object_id, stem in base_ownership.items():
        ownership.setdefault(object_id, stem)
        if object_id not in coordinates:
            obj = objects[object_indexes[object_id]]
            coordinates[object_id] = [obj.x, obj.y, obj.z]

    missing_clusters = locked_stems - set(clusters)
    if missing_clusters:
        raise RuntimeError(f"Missing locked clusters: {sorted(missing_clusters)}")

    fingerprint = "\n".join(
        f"{object_id}={stem}"
        for object_id, stem in sorted(ownership.items())
    )
    payload = {
        "version": 3,
        "polities": expected,
        "baseOwnership": dict(sorted(base_ownership.items())),
        "ownership": dict(sorted(ownership.items())),
        "clusters": {
            stem: [obj.id for obj in cluster]
            for stem, cluster in sorted(clusters.items())
        },
        "coordinates": {
            object_id: coordinates[object_id]
            for object_id in sorted(coordinates)
        },
        "fingerprint": hashlib.sha256(fingerprint.encode()).hexdigest(),
    }
    OUTPUT.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(
        f"Wrote {OUTPUT} with {len(base_ownership)} base and "
        f"{len(ownership)} total assignments "
        f"(fingerprint {payload['fingerprint']})"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
