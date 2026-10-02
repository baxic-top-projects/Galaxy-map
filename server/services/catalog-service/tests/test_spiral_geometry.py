from collections import Counter, defaultdict
from math import cos, hypot, sin
import re
from types import SimpleNamespace

from app.service.spiral_arm_service import _generated_claim_catalog, gateway_edges
from app.service.spiral_geometry import (
    ARM_COUNT,
    BLACK_HOLES_PER_ARM,
    ID_PREFIX,
    JUNCTIONS_PER_ARM,
    OBJECTS_PER_ARM,
    OUTER_RADIUS,
    STARS_PER_ARM,
    arm_center,
    arm_edges,
    arm_progress,
    generate_arm_objects,
)


def test_spiral_object_counts_and_stable_bounds():
    first = generate_arm_objects()
    second = generate_arm_objects()
    assert first == second
    assert len(first) == ARM_COUNT * OBJECTS_PER_ARM
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


def test_claimed_objects_receive_stable_names():
    by_kind = {}
    for obj in generate_arm_objects():
        by_kind.setdefault(obj.kind, obj)

    for obj in by_kind.values():
        catalog = _generated_claim_catalog(obj, "Test_Polity")
        assert catalog["token"]
        assert catalog["nameEn"]
        assert catalog["nameRu"]
        assert catalog["kind"] == obj.kind
        assert re.fullmatch(r"[A-Za-z ]+", catalog["nameEn"])
        assert re.fullmatch(r"[А-Яа-яЁё ]+", catalog["nameRu"])


def test_arm_distribution_is_wide_at_disk_and_tapers_toward_tip():
    deviations = {"base": [], "tip": []}
    for obj in generate_arm_objects():
        progress = arm_progress(obj.ordinal)
        center_x, center_y = arm_center(obj.arm - 1, progress)
        radius = hypot(center_x, center_y)
        normal_x = -center_y / radius
        normal_y = center_x / radius
        deviation = abs(
            (obj.x - center_x) * normal_x + (obj.y - center_y) * normal_y
        )
        if obj.ordinal < 40:
            deviations["base"].append(deviation)
        elif obj.ordinal >= OBJECTS_PER_ARM - 40:
            deviations["tip"].append(deviation)

    base_mean = sum(deviations["base"]) / len(deviations["base"])
    tip_mean = sum(deviations["tip"]) / len(deviations["tip"])
    assert max(deviations["base"]) > 0.05
    assert base_mean > tip_mean * 2


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


def test_arm_edges_stay_local_after_frontier_relocation():
    from app.service.frontier_polities import (
        allocate_new_frontier_polities,
        load_locked_frontier_layout,
    )
    from app.service.spiral_geometry import (
        MAX_LOCAL_EDGE_LENGTH,
        resync_arm_ordinals,
    )

    generated = generate_arm_objects()
    _, _, locked_ownership = load_locked_frontier_layout(generated)
    allocate_new_frontier_polities(
        generated,
        set(locked_ownership),
        locked_ownership,
    )
    resync_arm_ordinals(generated)
    by_id = {obj.id: obj for obj in generated}
    edges = arm_edges(generated)
    lengths = [
        hypot(by_id[a].x - by_id[b].x, by_id[a].y - by_id[b].y)
        for a, b in edges
    ]
    assert max(lengths) <= 0.35
    # Lookaround extras are hard-capped; MST spans may be a bit longer.
    lookaround_like = sum(1 for length in lengths if length > MAX_LOCAL_EDGE_LENGTH)
    assert lookaround_like < len(edges) * 0.02
