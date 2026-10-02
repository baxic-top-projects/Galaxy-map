from __future__ import annotations

import hashlib
import math
from dataclasses import dataclass, replace

ARM_COUNT = 4
STARS_PER_ARM = 1290
BLACK_HOLES_PER_ARM = 43
JUNCTIONS_PER_ARM = 25
OBJECTS_PER_ARM = STARS_PER_ARM + BLACK_HOLES_PER_ARM + JUNCTIONS_PER_ARM
INNER_RADIUS = 1.00
OUTER_RADIUS = 2.61
MAP_LIMIT = 2.80
SPIRAL_TURN_RADIANS = 3.20
ARM_PHASE_RADIANS = 0.144
ARM_HALF_WIDTH_BASE = 1.62
ARM_HALF_WIDTH_TIP = 0.315
ARM_PROGRESS_EXPONENT = 1.80
GENERATOR_SEED = 20260930
ID_PREFIX = "frontier:"
# Local lookaround corridors must stay short; relocated specials can keep a stale
# ordinal, and an ordinal-only neighbor window would otherwise draw base↔tip links.
MAX_LOCAL_EDGE_LENGTH = 0.14
MAX_LOCAL_EDGE_LENGTH_SQ = MAX_LOCAL_EDGE_LENGTH * MAX_LOCAL_EDGE_LENGTH
# Prim may still bridge relocated specials across an arm; drop those spans.
MAX_SPAN_EDGE_LENGTH = 0.35
MAX_SPAN_EDGE_LENGTH_SQ = MAX_SPAN_EDGE_LENGTH * MAX_SPAN_EDGE_LENGTH

def _spread_slots(count: int, occupied: frozenset[int] = frozenset()) -> frozenset[int]:
    slots: set[int] = set()
    for index in range(count):
        target = int((index + 0.5) * OBJECTS_PER_ARM / count)
        for distance in range(OBJECTS_PER_ARM):
            candidates = (target + distance, target - distance)
            slot = next(
                (
                    candidate
                    for candidate in candidates
                    if 0 <= candidate < OBJECTS_PER_ARM
                    and candidate not in occupied
                    and candidate not in slots
                ),
                None,
            )
            if slot is not None:
                slots.add(slot)
                break
    return frozenset(slots)


_BLACK_HOLE_SLOTS = _spread_slots(BLACK_HOLES_PER_ARM)
_JUNCTION_SLOTS = _spread_slots(JUNCTIONS_PER_ARM, _BLACK_HOLE_SLOTS)
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


def arm_progress(slot: int) -> float:
    """Bias systems toward the broad attachment while retaining the full arm."""
    return ((slot + 0.5) / OBJECTS_PER_ARM) ** ARM_PROGRESS_EXPONENT


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
            progress = arm_progress(slot)
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
            # Express arm width as an angular spread. At the broad attachment
            # this keeps every object next to the old circular disk instead of
            # pushing edge objects far outward with a Cartesian tangent offset.
            object_angle = angle + normal_offset / max(radius, 0.001)
            x = radius * math.cos(object_angle)
            y = radius * math.sin(object_angle)
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


def resync_arm_ordinals(objects: list[ArmObject]) -> None:
    """Reassign ordinals from current coordinates so local edge windows stay local.

    Relocated black holes / junctions keep their generator slot ordinal unless
    this runs after coordinate overrides. Ordering by radius along each arm is a
    stable proxy for spiral progress (inner base → outer tip).
    """
    by_arm: dict[int, list[int]] = {}
    for index, obj in enumerate(objects):
        by_arm.setdefault(obj.arm, []).append(index)
    for indexes in by_arm.values():
        ordered = sorted(
            indexes,
            key=lambda index: (
                math.hypot(objects[index].x, objects[index].y),
                objects[index].id,
            ),
        )
        for ordinal, index in enumerate(ordered):
            if objects[index].ordinal != ordinal:
                objects[index] = replace(objects[index], ordinal=ordinal)


def arm_edges(objects: list[ArmObject]) -> set[tuple[str, str]]:
    by_arm: dict[int, list[ArmObject]] = {}
    for obj in objects:
        by_arm.setdefault(obj.arm, []).append(obj)

    edges: set[tuple[str, str]] = set()
    for arm_objects in by_arm.values():
        ordered = sorted(arm_objects, key=lambda item: item.ordinal)
        # Connect the cloud with an O(n²) Prim tree. This avoids both a single
        # striped chain and long first-to-second links across the broad base.
        count = len(ordered)
        in_tree = [False] * count
        best_distance = [math.inf] * count
        best_parent = [-1] * count
        best_distance[0] = 0.0
        for _ in range(count):
            current = min(
                (
                    best_distance[index],
                    ordered[index].id,
                    index,
                )
                for index in range(count)
                if not in_tree[index]
            )[2]
            in_tree[current] = True
            parent = best_parent[current]
            if (
                parent >= 0
                and best_distance[current] <= MAX_SPAN_EDGE_LENGTH_SQ
            ):
                edges.add(
                    tuple(sorted((ordered[current].id, ordered[parent].id)))
                )
            for candidate in range(count):
                if in_tree[candidate]:
                    continue
                distance = (
                    (ordered[current].x - ordered[candidate].x) ** 2
                    + (ordered[current].y - ordered[candidate].y) ** 2
                )
                if distance < best_distance[candidate]:
                    best_distance[candidate] = distance
                    best_parent[candidate] = current

        lookaround = 32
        for index, obj in enumerate(ordered):
            # Add two local neighbors to create branches and short loops across
            # the arm width instead of a single visible corridor stripe.
            nearest = sorted(
                (
                    (
                        (obj.x - other.x) ** 2 + (obj.y - other.y) ** 2,
                        other.id,
                    )
                    for other_index, other in enumerate(ordered)
                    if other_index != index
                    and abs(other_index - index) <= lookaround
                ),
            )[:2]
            for distance_sq, neighbor_id in nearest:
                if distance_sq > MAX_LOCAL_EDGE_LENGTH_SQ:
                    continue
                edges.add(tuple(sorted((obj.id, neighbor_id))))
    return edges
