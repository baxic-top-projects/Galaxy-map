"""Freeze the current frontier polity layout for stable future ownership."""

from __future__ import annotations

import hashlib
import json
import sys
from collections import defaultdict
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
)
from app.service.spiral_geometry import ArmObject, generate_arm_objects  # noqa: E402


def _cluster_from_owned(
    object_ids: list[str],
    by_id: dict,
    *,
    objects: list,
    object_indexes: dict[str, int],
    coordinates: dict[str, list[float]],
    ownership: dict[str, str],
    stem: str,
    side: int,
) -> list[str]:
    """Pick a stable 20-star core (+ specials), minting shortfall into the lock."""
    owned = [by_id[object_id] for object_id in object_ids if object_id in by_id]
    stars = sorted(
        (obj for obj in owned if obj.kind == "star"),
        key=lambda obj: (obj.ordinal, obj.id),
    )
    specials = []
    for kind in ("black_hole", "junction"):
        matches = sorted(
            (obj for obj in owned if obj.kind == kind),
            key=lambda obj: (obj.ordinal, obj.id),
        )
        if matches:
            specials.append(matches[0])

    if stars:
        center_x = sum(obj.x for obj in stars) / len(stars)
        center_y = sum(obj.y for obj in stars) / len(stars)
        arm = stars[0].arm
        ordinal = stars[len(stars) // 2].ordinal
    else:
        center_x = float(side) * 0.5
        center_y = 0.0
        arm = 1 if side > 0 else 2
        ordinal = 0

    cluster_stars = list(stars[:20])
    mint_index = 0
    while len(cluster_stars) < 20:
        extra_index = sum(
            1 for obj in objects if obj.kind == "star" and "-extra-" in obj.id
        )
        angle = (extra_index + mint_index) * 2.399963229728653
        radius = 0.012 + (mint_index % 5) * 0.007
        x = center_x + __import__("math").cos(angle) * radius
        y = center_y + __import__("math").sin(angle) * radius
        if x * side <= 0:
            x = center_x + side * radius
        minted_id = f"frontier:arm-{arm}:star-extra-{extra_index:03d}"
        minted = ArmObject(
            id=minted_id,
            arm=arm,
            ordinal=ordinal,
            kind="star",
            star_type_key="class_g",
            x=round(x, 6),
            y=round(y, 6),
            z=0.0,
        )
        objects.append(minted)
        object_indexes[minted.id] = len(objects) - 1
        by_id[minted.id] = minted
        coordinates[minted.id] = [minted.x, minted.y, minted.z]
        ownership[minted.id] = stem
        cluster_stars.append(minted)
        mint_index += 1

    return [obj.id for obj in (*cluster_stars, *specials)]


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

    expected = [polity.stem for polity in LOCKED_FRONTIER_POLITIES]
    locked_stems = set(expected)
    if len(expected) != 105:
        raise RuntimeError(f"Expected 105 locked polities, got {len(expected)}")

    galaxy = requests.get(GALAXY_API, timeout=180).json()
    ownership: dict[str, str] = {}
    coordinates: dict[str, list[float]] = {}
    owned_by_stem: dict[str, list[str]] = defaultdict(list)

    for system in galaxy.get("systems") or []:
        system_id = str(system.get("id") or "")
        stem = system.get("stem")
        if not system_id.startswith("frontier:") or stem not in locked_stems:
            continue
        ownership[system_id] = stem
        owned_by_stem[stem].append(system_id)
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
            continue
        kind = str(system.get("kind") or "star")
        if kind not in {"star", "black_hole", "junction"}:
            kind = "star"
        arm = 1
        if ":arm-" in system_id:
            try:
                arm = int(system_id.split(":arm-", 1)[1].split(":", 1)[0])
            except ValueError:
                arm = 1
        objects.append(
            ArmObject(
                id=system_id,
                arm=arm,
                ordinal=len(objects),
                kind=kind,
                star_type_key=(
                    "black_hole"
                    if kind == "black_hole"
                    else "junction"
                    if kind == "junction"
                    else str(system.get("starTypeKey") or "class_g")
                ),
                x=float(system["x"]),
                y=float(system["y"]),
                z=float(system["z"]),
            )
        )
        object_indexes[system_id] = len(objects) - 1

    by_id = {obj.id: obj for obj in objects}
    prior_clusters = prior_lock.get("clusters") or {}
    prior_base = prior_lock.get("baseOwnership") or {}
    clusters: dict[str, list[str]] = {}
    base_ownership: dict[str, str] = {}

    missing_live = locked_stems - set(owned_by_stem)
    if missing_live:
        raise RuntimeError(
            "Live map is missing locked polities: "
            + ", ".join(sorted(missing_live))
        )

    side_by_stem = {polity.stem: polity.side for polity in LOCKED_FRONTIER_POLITIES}
    for stem in expected:
        cluster_ids = _cluster_from_owned(
            owned_by_stem[stem],
            by_id,
            objects=objects,
            object_indexes=object_indexes,
            coordinates=coordinates,
            ownership=ownership,
            stem=stem,
            side=side_by_stem[stem],
        )
        # Prefer a prior compact core only when it still has exactly 20 stars.
        prior_ids = prior_clusters.get(stem) or []
        if prior_ids and all(object_id in by_id for object_id in prior_ids):
            prior_star_count = sum(
                1 for object_id in prior_ids if by_id[object_id].kind == "star"
            )
            if prior_star_count == 20:
                cluster_ids = list(prior_ids)
        clusters[stem] = cluster_ids
        for object_id in cluster_ids:
            base_ownership[object_id] = stem
            if object_id not in coordinates:
                obj = by_id[object_id]
                coordinates[object_id] = [obj.x, obj.y, obj.z]
            ownership.setdefault(object_id, stem)

    # Preserve prior base ids when they still belong to the same stem.
    for object_id, stem in prior_base.items():
        if stem in locked_stems and ownership.get(object_id) == stem:
            base_ownership.setdefault(object_id, stem)

    fingerprint = "\n".join(
        f"{object_id}={stem}"
        for object_id, stem in sorted(ownership.items())
    )
    payload = {
        "version": 4,
        "polities": expected,
        "baseOwnership": dict(sorted(base_ownership.items())),
        "ownership": dict(sorted(ownership.items())),
        "clusters": {
            stem: clusters[stem]
            for stem in expected
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
        f"{len(ownership)} total assignments across {len(expected)} polities "
        f"(fingerprint {payload['fingerprint']})"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
