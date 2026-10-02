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

    # Prefer the previously published lock for the original 21 polities so that
    # their expanded ownership and relocated specials stay byte-stable.
    prior_lock = {}
    if OUTPUT.is_file():
        prior_lock = json.loads(OUTPUT.read_text(encoding="utf-8"))

    original_stems = [polity.stem for polity in ORIGINAL_FRONTIER_POLITIES]
    if prior_lock.get("polities") == original_stems:
        for object_id, coordinates in prior_lock["coordinates"].items():
            index = object_indexes.get(object_id)
            if index is None:
                continue
            objects[index] = replace(
                objects[index],
                x=float(coordinates[0]),
                y=float(coordinates[1]),
                z=float(coordinates[2]),
            )
        by_id = {obj.id: obj for obj in objects}
        original_base = dict(prior_lock["baseOwnership"])
        original_clusters = {
            stem: tuple(by_id[object_id] for object_id in object_ids)
            for stem, object_ids in prior_lock["clusters"].items()
        }
        original_ownership = dict(prior_lock["ownership"])
    else:
        original_base, original_clusters = allocate_frontier_polities(objects)
        original_ownership = dict(original_base)

    previous_ownership, previous_clusters = allocate_new_frontier_polities(
        objects,
        original_ownership,
        original_ownership,
        polities=PREVIOUS_FRONTIER_POLITIES,
    )

    clusters = {**original_clusters, **previous_clusters}
    base_ownership = {**original_base, **previous_ownership}
    object_indexes = {obj.id: index for index, obj in enumerate(objects)}

    locked_stems = {polity.stem for polity in LOCKED_FRONTIER_POLITIES}
    expected = [polity.stem for polity in LOCKED_FRONTIER_POLITIES]
    if len(ORIGINAL_FRONTIER_POLITIES) + len(PREVIOUS_FRONTIER_POLITIES) != len(
        LOCKED_FRONTIER_POLITIES
    ):
        raise RuntimeError("Locked frontier waves do not cover every locked polity")

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

    # Keep every base cluster object owned even if the live API briefly lags.
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
        "version": 2,
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
