from __future__ import annotations

import math

from sqlalchemy import delete, func, or_, select

from app.db.models import EdgeRow, GalaxyMetaRow, SessionLocal, SystemRow
from app.service.spiral_geometry import (
    ARM_COUNT,
    BLACK_HOLES_PER_ARM,
    GENERATOR_SEED,
    ID_PREFIX,
    JUNCTIONS_PER_ARM,
    MAP_LIMIT,
    OUTER_RADIUS,
    STARS_PER_ARM,
    ArmObject,
    arm_edges,
    generate_arm_objects,
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


def _index_payload(obj: ArmObject) -> dict:
    shard_name = obj.id.replace(":", "__") + ".json"
    return {
        "id": obj.id,
        "token": "",
        "stem": None,
        "kind": obj.kind,
        "nameEn": "",
        "nameRu": "",
        "starTypeKey": obj.star_type_key,
        "sectorId": "",
        "capital": False,
        "x": obj.x,
        "y": obj.y,
        "z": obj.z,
        "worldCount": 0,
        "shard": f"systems/{shard_name}",
    }


def _detail_payload(obj: ArmObject) -> dict:
    return {
        **_index_payload(obj),
        "starType": _star_type_name(obj.star_type_key),
        "sectorNameEn": "",
        "worlds": [],
        "uninhabited": [],
        "features": [],
        "frontierArm": obj.arm,
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
    generated_ids = {obj.id for obj in generated}

    with SessionLocal() as session:
        existing = list(session.scalars(select(SystemRow)))
        gateways = gateway_edges(generated, existing)
        generated_edges = arm_edges(generated) | gateways

        for obj in generated:
            payload = _detail_payload(obj)
            session.merge(
                SystemRow(
                    id=obj.id,
                    token="",
                    stem=None,
                    kind=obj.kind,
                    name_en="",
                    name_ru="",
                    star_type_key=obj.star_type_key,
                    sector_id="",
                    capital=False,
                    x=obj.x,
                    y=obj.y,
                    z=obj.z,
                    world_count=0,
                    shard=payload["shard"],
                    detail=payload,
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
        meta_payload.update(
            {
                "mapLim": MAP_LIMIT,
                "centralDiskR": 1.02,
                "spiralArmCount": ARM_COUNT,
                "spiralOuterRadius": OUTER_RADIUS,
                "spiralSeed": GENERATOR_SEED,
                "spiralStars": ARM_COUNT * STARS_PER_ARM,
                "spiralBlackHoles": ARM_COUNT * BLACK_HOLES_PER_ARM,
                "spiralJunctions": ARM_COUNT * JUNCTIONS_PER_ARM,
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
    }
