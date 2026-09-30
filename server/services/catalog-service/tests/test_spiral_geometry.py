from collections import Counter, defaultdict
from math import cos, hypot, sin
from types import SimpleNamespace

from app.service.spiral_arm_service import gateway_edges
from app.service.spiral_geometry import (
    ARM_COUNT,
    BLACK_HOLES_PER_ARM,
    ID_PREFIX,
    JUNCTIONS_PER_ARM,
    OUTER_RADIUS,
    STARS_PER_ARM,
    arm_edges,
    generate_arm_objects,
)


def test_spiral_object_counts_and_stable_bounds():
    first = generate_arm_objects()
    second = generate_arm_objects()
    assert first == second
    assert len(first) == 632
    assert len({obj.id for obj in first}) == len(first)
    assert all(obj.id.startswith(ID_PREFIX) for obj in first)
    assert max(hypot(obj.x, obj.y) for obj in first) <= OUTER_RADIUS + 0.02

    by_arm = defaultdict(Counter)
    for obj in first:
        by_arm[obj.arm][obj.kind] += 1
    assert len(by_arm) == ARM_COUNT
    for counts in by_arm.values():
        assert counts == {
            "star": STARS_PER_ARM,
            "black_hole": BLACK_HOLES_PER_ARM,
            "junction": JUNCTIONS_PER_ARM,
        }


def test_each_arm_is_connected_without_cross_arm_corridors():
    generated = generate_arm_objects()
    edges = arm_edges(generated)
    adjacency = defaultdict(set)
    for a, b in edges:
        adjacency[a].add(b)
        adjacency[b].add(a)

    for arm in range(1, ARM_COUNT + 1):
        ids = {obj.id for obj in generated if obj.arm == arm}
        seen = set()
        stack = [next(iter(ids))]
        while stack:
            current = stack.pop()
            if current in seen:
                continue
            seen.add(current)
            stack.extend(adjacency[current] - seen)
        assert seen == ids
    arm_by_id = {obj.id: obj.arm for obj in generated}
    assert all(arm_by_id[a] == arm_by_id[b] for a, b in edges)

    existing = [
        SimpleNamespace(
            id=f"existing:{index}",
            kind="star",
            x=0.96 * cos(index * 0.25),
            y=0.96 * sin(index * 0.25),
        )
        for index in range(26)
    ]
    gateways = gateway_edges(generated, existing)
    assert len(gateways) >= ARM_COUNT * 8
    assert all(
        (a.startswith(ID_PREFIX) and b.startswith("existing:"))
        or (b.startswith(ID_PREFIX) and a.startswith("existing:"))
        for a, b in gateways
    )
    stitched_arms = {
        arm_by_id[a] if a.startswith(ID_PREFIX) else arm_by_id[b]
        for a, b in gateways
    }
    assert stitched_arms == set(range(1, ARM_COUNT + 1))
