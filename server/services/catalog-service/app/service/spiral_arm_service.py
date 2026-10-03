from __future__ import annotations

import math

from sqlalchemy import delete, func, or_, select

from app.db.models import (
    EdgeRow,
    GalaxyMetaRow,
    PolityRow,
    SearchEntryRow,
    SessionLocal,
    SystemOwnerOverrideRow,
    SystemRow,
)
from app.service.frontier_polities import (
    FRONTIER_POLITIES,
    NEW_FRONTIER_ARM_BY_STEM,
    NEW_FRONTIER_SIDE_BY_STEM,
    NEW_FRONTIER_STEMS,
    allocate_new_frontier_polities,
    assign_objects_inside_territories,
    load_locked_frontier_layout,
    map_canonical_frontier_catalog,
)
from app.service.frontier_naming import (
    generated_frontier_worlds,
    natural_frontier_black_hole_name,
    natural_frontier_junction_name,
    natural_frontier_star_name,
)
from app.service.spiral_geometry import (
    ARM_COUNT,
    GENERATOR_SEED,
    ID_PREFIX,
    MAP_LIMIT,
    OUTER_RADIUS,
    ArmObject,
    arm_edges,
    generate_arm_objects,
    resync_arm_ordinals,
)


def _star_type_name(type_key: str) -> str:
    return {
        "class_m": "Class M",
        "class_k": "Class K",
        "class_g": "Class G",
        "class_f": "Class F",
        "class_a": "Class A",
        "class_b": "Class B",
        "black_hole": "Black Hole",
        "junction": "Empty hypercorridor node",
    }[type_key]


def _index_payload(
    obj: ArmObject,
    stem: str | None = None,
    canonical: dict | None = None,
) -> dict:
    shard_name = obj.id.replace(":", "__") + ".json"
    canonical = canonical or {}
    return {
        "id": obj.id,
        "token": canonical.get("token") or "",
        "stem": stem,
        "kind": obj.kind,
        "nameEn": canonical.get("nameEn") or "",
        "nameRu": canonical.get("nameRu") or "",
        "starTypeKey": canonical.get("starTypeKey") or obj.star_type_key,
        "sectorId": canonical.get("sectorId") or "",
        "capital": False,
        "x": obj.x,
        "y": obj.y,
        "z": obj.z,
        "worldCount": len(canonical.get("worlds") or []),
        "territoryAnchor": canonical.get("territoryAnchor", True),
        "shard": f"systems/{shard_name}",
    }


def _detail_payload(
    obj: ArmObject,
    stem: str | None = None,
    canonical: dict | None = None,
) -> dict:
    canonical = canonical or {}
    return {
        **_index_payload(obj, stem, canonical),
        "canonicalId": canonical.get("canonicalId"),
        "starType": canonical.get("starType") or _star_type_name(obj.star_type_key),
        "sectorNameEn": canonical.get("sectorNameEn") or "",
        "worlds": canonical.get("worlds") or [],
        "uninhabited": canonical.get("uninhabited") or [],
        "features": canonical.get("features") or [],
        "frontierArm": obj.arm,
    }


def _generated_claim_catalog(
    obj: ArmObject,
    stem: str,
    *,
    territory_anchor: bool = True,
) -> dict:
    if obj.kind == "star":
        token, name_en, name_ru = natural_frontier_star_name(obj.id)
    elif obj.kind == "black_hole":
        token, name_en, name_ru = natural_frontier_black_hole_name(obj.id)
    else:
        token, name_en, name_ru = natural_frontier_junction_name(obj.id)
    return {
        "canonicalId": None,
        "token": token,
        "kind": obj.kind,
        "nameEn": name_en,
        "nameRu": name_ru,
        "starType": _star_type_name(obj.star_type_key),
        "starTypeKey": obj.star_type_key,
        "sectorId": "",
        "sectorNameEn": "",
        "worlds": [],
        "uninhabited": [],
        "features": [],
        "territoryAnchor": territory_anchor,
    }


def _ensure_frontier_star_worlds(obj: ArmObject, canonical: dict) -> dict:
    if (
        obj.kind != "star"
        or not canonical.get("token")
        or canonical.get("worlds")
    ):
        return canonical
    return {
        **canonical,
        "worlds": generated_frontier_worlds(obj.id, canonical["token"]),
    }


def gateway_edges(
    generated: list[ArmObject],
    existing: list[SystemRow],
) -> set[tuple[str, str]]:
    eligible = [
        row
        for row in existing
        if not row.id.startswith(ID_PREFIX)
        and row.kind in {"star", "black_hole", "junction"}
        and math.hypot(row.x, row.y) >= 0.70
    ]
    edges: set[tuple[str, str]] = set()
    for arm in range(1, ARM_COUNT + 1):
        seam = sorted(
            (obj for obj in generated if obj.arm == arm and obj.ordinal < 18),
            key=lambda obj: obj.ordinal,
        )
        for entry in seam:
            nearest = sorted(
                eligible,
                key=lambda row: (
                    math.hypot(row.x - entry.x, row.y - entry.y),
                    row.id,
                ),
            )[:2]
            local = [
                row
                for row in nearest
                if math.hypot(row.x - entry.x, row.y - entry.y) <= 0.11
            ]
            for row in local or nearest[:1]:
                edges.add(tuple(sorted((entry.id, row.id))))
    return edges


def apply_spiral_extension() -> dict[str, int]:
    generated = generate_arm_objects()
    locked_base, locked_clusters, locked_ownership = (
        load_locked_frontier_layout(generated)
    )
    # Layout lock may append legacy black_hole/junction extras that already render
    # on the map. Include them in generated_ids so sync does not delete them and
    # the public systemCount stays stable across deploys (9063).
    generated_ids = {obj.id for obj in generated}

    with SessionLocal() as session:
        existing = list(session.scalars(select(SystemRow)))
        manual_ownership = {
            row.system_id: row.stem
            for row in session.scalars(select(SystemOwnerOverrideRow))
        }
        new_ownership, new_clusters = allocate_new_frontier_polities(
            generated,
            {*locked_ownership, *manual_ownership},
            locked_ownership,
        )
        ownership = {**locked_ownership, **new_ownership}
        clusters = {**locked_clusters, **new_clusters}
        by_id = {obj.id: obj for obj in generated}
        territory_ownership = {
            object_id: stem
            for object_id, stem in assign_objects_inside_territories(
                generated,
                ownership,
                existing,
            ).items()
            if stem in NEW_FRONTIER_STEMS
            and by_id[object_id].arm == NEW_FRONTIER_ARM_BY_STEM[stem]
            # Miradin vassals stay on the right (+x); Raih on the left (-x).
            and by_id[object_id].x * NEW_FRONTIER_SIDE_BY_STEM[stem] > 0
        }
        ownership.update(territory_ownership)
        canonical_catalog = map_canonical_frontier_catalog(clusters)
        for object_id, stem in ownership.items():
            canonical_catalog.setdefault(
                object_id,
                _generated_claim_catalog(
                    by_id[object_id],
                    stem,
                ),
            )
        for object_id, stem in manual_ownership.items():
            obj = by_id.get(object_id)
            if (
                obj is None
                or obj.kind != "star"
                or object_id in canonical_catalog
            ):
                continue
            generated_entry = _generated_claim_catalog(obj, stem)
            generated_entry["worlds"] = generated_frontier_worlds(
                obj.id,
                generated_entry["token"],
            )
            canonical_catalog[object_id] = generated_entry
        canonical_catalog = {
            object_id: _ensure_frontier_star_worlds(
                by_id[object_id],
                canonical,
            )
            for object_id, canonical in canonical_catalog.items()
        }
        effective_ownership = {**ownership, **manual_ownership}
        resync_arm_ordinals(generated)
        gateways = gateway_edges(generated, existing)
        generated_edges = arm_edges(generated) | gateways

        for polity in FRONTIER_POLITIES:
            session.merge(PolityRow(stem=polity.stem, payload=polity.payload()))

        for obj in generated:
            stem = ownership.get(obj.id)
            payload = _detail_payload(obj, stem, canonical_catalog.get(obj.id))
            session.merge(
                SystemRow(
                    id=obj.id,
                    token=payload["token"],
                    stem=stem,
                    kind=obj.kind,
                    name_en=payload["nameEn"],
                    name_ru=payload["nameRu"],
                    star_type_key=payload["starTypeKey"],
                    sector_id=payload["sectorId"],
                    capital=False,
                    x=obj.x,
                    y=obj.y,
                    z=obj.z,
                    world_count=payload["worldCount"],
                    shard=payload["shard"],
                    detail=payload,
                )
            )

        session.execute(
            delete(SearchEntryRow).where(
                SearchEntryRow.entry_key.like(f"%:{ID_PREFIX}%")
            )
        )
        for system_id, canonical in sorted(canonical_catalog.items()):
            stem = effective_ownership[system_id]
            if canonical["kind"] != "junction":
                session.add(
                    SearchEntryRow(
                        entry_key=f"system:{system_id}:{canonical['token']}",
                        payload={
                            "id": system_id,
                            "kind": "system",
                            "token": canonical["token"],
                            "nameEn": canonical["nameEn"],
                            "nameRu": canonical["nameRu"],
                            "stem": stem,
                        },
                    )
                )
            for world in canonical.get("worlds") or []:
                session.add(
                    SearchEntryRow(
                        entry_key=f"world:{system_id}:{world['token']}",
                        payload={
                            "id": system_id,
                            "kind": "world",
                            "token": world["token"],
                            "nameEn": world["nameEn"],
                            "nameRu": world["nameRu"],
                            "stem": stem,
                            "planetTypeKey": world.get(
                                "planetTypeKey",
                                "continental",
                            ),
                        },
                    )
                )

        stale_ids = {
            row.id
            for row in existing
            if row.id.startswith(ID_PREFIX) and row.id not in generated_ids
        }
        if stale_ids:
            session.execute(delete(SystemRow).where(SystemRow.id.in_(stale_ids)))

        session.execute(
            delete(EdgeRow).where(
                or_(
                    EdgeRow.a.like(f"{ID_PREFIX}%"),
                    EdgeRow.b.like(f"{ID_PREFIX}%"),
                )
            )
        )
        for graph in ("canon", "display"):
            for a, b in sorted(generated_edges):
                session.add(EdgeRow(a=a, b=b, graph=graph))

        session.flush()
        system_count = int(session.scalar(select(func.count()).select_from(SystemRow)) or 0)
        canon_count = int(
            session.scalar(
                select(func.count())
                .select_from(EdgeRow)
                .where(EdgeRow.graph == "canon")
            )
            or 0
        )
        display_count = int(
            session.scalar(
                select(func.count())
                .select_from(EdgeRow)
                .where(EdgeRow.graph == "display")
            )
            or 0
        )
        meta = session.get(GalaxyMetaRow, 1)
        meta_payload = dict(meta.payload or {}) if meta else {}
        spiral_stars = sum(1 for obj in generated if obj.kind == "star")
        spiral_black_holes = sum(1 for obj in generated if obj.kind == "black_hole")
        spiral_junctions = sum(1 for obj in generated if obj.kind == "junction")
        meta_payload.update(
            {
                "mapLim": MAP_LIMIT,
                "centralDiskR": 1.10,
                "spiralArmCount": ARM_COUNT,
                "spiralOuterRadius": OUTER_RADIUS,
                "spiralSeed": GENERATOR_SEED,
                "spiralStars": spiral_stars,
                "spiralBlackHoles": spiral_black_holes,
                "spiralJunctions": spiral_junctions,
                "frontierPolities": len(FRONTIER_POLITIES),
                "frontierAssignedSystems": len(ownership),
                "frontierTerritoryClaims": (
                    len(locked_ownership)
                    - len(locked_base)
                    + len(territory_ownership)
                ),
                "frontierNamedSystems": len(canonical_catalog),
                "systemCount": system_count,
                "edgeCountCanon": canon_count,
                "edgeCountDisplay": display_count,
            }
        )
        session.merge(GalaxyMetaRow(id=1, payload=meta_payload))
        session.commit()

    return {
        "systems": len(generated),
        "edgesPerGraph": len(generated_edges),
        "gateways": len(gateways),
        "polities": len(clusters),
        "assignedSystems": len(ownership),
        "territoryClaims": (
            len(locked_ownership)
            - len(locked_base)
            + len(territory_ownership)
        ),
        "namedSystems": len(canonical_catalog),
    }
