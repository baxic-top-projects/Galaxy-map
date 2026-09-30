from __future__ import annotations

import hashlib
import math
from dataclasses import dataclass

ARM_COUNT = 4
STARS_PER_ARM = 150
BLACK_HOLES_PER_ARM = 5
JUNCTIONS_PER_ARM = 3
OBJECTS_PER_ARM = STARS_PER_ARM + BLACK_HOLES_PER_ARM + JUNCTIONS_PER_ARM
INNER_RADIUS = 1.02
OUTER_RADIUS = 1.55
MAP_LIMIT = 1.80
SPIRAL_TURN_RADIANS = 1.00
ARM_PHASE_RADIANS = math.pi / 18
ARM_HALF_WIDTH_BASE = 0.18
ARM_HALF_WIDTH_TIP = 0.035
GENERATOR_SEED = 20260930
ID_PREFIX = "frontier:"

_BLACK_HOLE_SLOTS = frozenset({18, 48, 82, 118, 146})
_JUNCTION_SLOTS = frozenset({38, 78, 124})
_STAR_TYPES = ("class_m", "class_k", "class_g", "class_f", "class_a", "class_b")


@dataclass(frozen=True)
class ArmObject:
    id: str
    arm: int
    ordinal: int
    kind: str
    star_type_key: str
    x: float
    y: float
    z: float


def _unit_hash(value: str, offset: int = 0) -> float:
    digest = hashlib.sha256(f"{GENERATOR_SEED}:{value}".encode()).digest()
    raw = int.from_bytes(digest[offset : offset + 4], "big")
    return raw / 0xFFFFFFFF


def arm_center(arm: int, progress: float) -> tuple[float, float]:
    radius = INNER_RADIUS + (OUTER_RADIUS - INNER_RADIUS) * progress
    angle = (
        ARM_PHASE_RADIANS
        + arm * math.tau / ARM_COUNT
        + SPIRAL_TURN_RADIANS * progress
    )
    return radius * math.cos(angle), radius * math.sin(angle)


def arm_object_kind(slot: int) -> str:
    if slot in _BLACK_HOLE_SLOTS:
        return "black_hole"
    if slot in _JUNCTION_SLOTS:
        return "junction"
    return "star"


def generate_arm_objects() -> list[ArmObject]:
    objects: list[ArmObject] = []
    for arm in range(ARM_COUNT):
        kind_counts = {"star": 0, "black_hole": 0, "junction": 0}
        for slot in range(OBJECTS_PER_ARM):
            progress = (slot + 0.5) / OBJECTS_PER_ARM
            kind = arm_object_kind(slot)
            kind_counts[kind] += 1
            ordinal = kind_counts[kind]
            object_id = f"{ID_PREFIX}arm-{arm + 1}:{kind}-{ordinal:03d}"

            center_x, center_y = arm_center(arm, progress)
            radius = math.hypot(center_x, center_y)
            angle = math.atan2(center_y, center_x)
            # Treat the arm as a curved triangle: its center follows the spiral
            # while its two sides converge linearly toward the outer tip.
            half_width = (
                ARM_HALF_WIDTH_TIP
                + (ARM_HALF_WIDTH_BASE - ARM_HALF_WIDTH_TIP)
                * (1.0 - progress)
            )
            across_arm = _unit_hash(object_id, 0) * 2.0 - 1.0
            normal_offset = across_arm * half_width
            radial_jitter = 0.018 * (1.0 - progress) + 0.006 * progress
            radial_offset = (_unit_hash(object_id, 4) - 0.5) * radial_jitter
            radius += radial_offset
            x = radius * math.cos(angle) - normal_offset * math.sin(angle)
            y = radius * math.sin(angle) + normal_offset * math.cos(angle)
            z = (_unit_hash(object_id, 8) * 2.0 - 1.0) * (0.018 - 0.008 * progress)

            if kind == "star":
                type_index = int(_unit_hash(object_id, 12) * len(_STAR_TYPES))
                star_type_key = _STAR_TYPES[min(type_index, len(_STAR_TYPES) - 1)]
            else:
                star_type_key = kind
            objects.append(
                ArmObject(
                    id=object_id,
                    arm=arm + 1,
                    ordinal=slot,
                    kind=kind,
                    star_type_key=star_type_key,
                    x=round(x, 6),
                    y=round(y, 6),
                    z=round(z, 6),
                )
            )
    return objects


def arm_edges(objects: list[ArmObject]) -> set[tuple[str, str]]:
    by_arm: dict[int, list[ArmObject]] = {}
    for obj in objects:
        by_arm.setdefault(obj.arm, []).append(obj)

    edges: set[tuple[str, str]] = set()
    for arm_objects in by_arm.values():
        ordered = sorted(arm_objects, key=lambda item: item.ordinal)
        # A minimum spanning tree connects the two-dimensional arm cloud with
        # local links instead of drawing one long stripe through every object.
        connected = {0}
        remaining = set(range(1, len(ordered)))
        while remaining:
            _, left_index, right_index = min(
                (
                    (ordered[left].x - ordered[right].x) ** 2
                    + (ordered[left].y - ordered[right].y) ** 2,
                    left,
                    right,
                )
                for left in connected
                for right in remaining
            )
            edges.add(
                tuple(sorted((ordered[left_index].id, ordered[right_index].id)))
            )
            connected.add(right_index)
            remaining.remove(right_index)

        # Add two local neighbors per object to form short branches and loops
        # across the arm width while keeping every corridor inside one arm.
        for index, obj in enumerate(ordered):
            nearest = sorted(
                (
                    (
                        (obj.x - other.x) ** 2 + (obj.y - other.y) ** 2,
                        other.id,
                    )
                    for other_index, other in enumerate(ordered)
                    if other_index != index
                ),
            )[:2]
            for _, neighbor_id in nearest:
                edges.add(tuple(sorted((obj.id, neighbor_id))))
    return edges
