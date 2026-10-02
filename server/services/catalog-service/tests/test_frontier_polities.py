import hashlib
from collections import Counter
from math import hypot

from app.service.frontier_polities import (
    FRONTIER_POLITIES,
    LOCKED_FRONTIER_POLITIES,
    NEW_FRONTIER_ARM_BY_STEM,
    NEW_FRONTIER_POLITIES,
    NEW_FRONTIER_STEMS,
    ORIGINAL_FRONTIER_POLITIES,
    PREVIOUS_FRONTIER_POLITIES,
    allocate_new_frontier_polities,
    allocate_frontier_polities,
    assign_objects_inside_territories,
    load_locked_frontier_layout,
    map_canonical_frontier_catalog,
)
from app.service.spiral_arm_service import (
    _ensure_frontier_star_worlds,
    _generated_claim_catalog,
)
from app.service.spiral_geometry import generate_arm_objects


def test_original_polities_receive_compact_single_arm_pockets():
    objects = generate_arm_objects()
    assignments, clusters = allocate_frontier_polities(objects)

    assert len(ORIGINAL_FRONTIER_POLITIES) == 21
    assert len(assignments) == 21 * 22
    assert sum(
        polity.bloc == "miradin"
        for polity in ORIGINAL_FRONTIER_POLITIES
    ) == 11
    assert sum(
        polity.bloc == "raih"
        for polity in ORIGINAL_FRONTIER_POLITIES
    ) == 10

    centers = []
    for polity in ORIGINAL_FRONTIER_POLITIES:
        cluster = clusters[polity.stem]
        assert Counter(obj.kind for obj in cluster) == {
            "star": 20,
            "black_hole": 1,
            "junction": 1,
        }
        assert {obj.arm for obj in cluster} == {polity.arm}
        assert all(obj.x * polity.side > 0 for obj in cluster)

        center_x = sum(obj.x for obj in cluster) / len(cluster)
        center_y = sum(obj.y for obj in cluster) / len(cluster)
        centers.append((center_x, center_y))
        assert hypot(center_x, center_y) < 1.15
        assert max(
            hypot(obj.x - center_x, obj.y - center_y) for obj in cluster
        ) < 0.17

    assert min(
        hypot(left[0] - right[0], left[1] - right[1])
        for index, left in enumerate(centers)
        for right in centers[index + 1 :]
    ) > 0.22


def test_missing_nearby_special_objects_are_relocated_into_pockets():
    original = {obj.id: obj for obj in generate_arm_objects()}
    objects = generate_arm_objects()
    _, clusters = allocate_frontier_polities(objects)

    relocated = 0
    for cluster in clusters.values():
        stars = [obj for obj in cluster if obj.kind == "star"]
        center_x = sum(obj.x for obj in stars) / len(stars)
        center_y = sum(obj.y for obj in stars) / len(stars)
        star_radius = max(
            hypot(obj.x - center_x, obj.y - center_y) for obj in stars
        )
        for obj in cluster:
            if obj.kind not in {"black_hole", "junction"}:
                continue
            assert hypot(obj.x - center_x, obj.y - center_y) <= max(
                0.081,
                star_radius * 1.21,
            )
            if (obj.x, obj.y) != (original[obj.id].x, original[obj.id].y):
                relocated += 1

    assert relocated > 0


def test_allocating_polities_does_not_move_any_stars():
    objects = generate_arm_objects()
    original = {
        obj.id: (obj.x, obj.y, obj.z)
        for obj in objects
        if obj.kind == "star"
    }
    allocate_frontier_polities(objects)

    assert {
        obj.id: (obj.x, obj.y, obj.z)
        for obj in objects
        if obj.kind == "star"
    } == original


def test_unclaimed_objects_inside_current_territories_get_owners():
    objects = generate_arm_objects()
    assignments, _ = allocate_frontier_polities(objects)
    additions = assign_objects_inside_territories(objects, assignments, [])
    by_id = {obj.id: obj for obj in objects}

    assert additions
    assert not additions.keys() & assignments.keys()
    assert {by_id[object_id].kind for object_id in additions} == {
        "star",
        "black_hole",
        "junction",
    }
    assert set(additions.values()) <= {
        polity.stem for polity in ORIGINAL_FRONTIER_POLITIES
    }


def test_locked_layout_preserves_current_forty_nine_polities():
    objects = generate_arm_objects()
    locked_base, locked_clusters, locked_ownership = (
        load_locked_frontier_layout(objects)
    )

    assert len(LOCKED_FRONTIER_POLITIES) == 49
    assert len(ORIGINAL_FRONTIER_POLITIES) == 21
    assert len(PREVIOUS_FRONTIER_POLITIES) == 28
    assert list(locked_clusters) == [
        polity.stem for polity in LOCKED_FRONTIER_POLITIES
    ] or set(locked_clusters) == {
        polity.stem for polity in LOCKED_FRONTIER_POLITIES
    }
    assert set(locked_clusters) == {
        polity.stem for polity in LOCKED_FRONTIER_POLITIES
    }
    assert len(locked_base) == 49 * 22
    assert len(locked_ownership) == 2840
    fingerprint = "\n".join(
        f"{object_id}={stem}"
        for object_id, stem in sorted(locked_ownership.items())
    )
    assert hashlib.sha256(fingerprint.encode()).hexdigest() == (
        "27679d3faad1bec9b99e11a4fd30c4988885fbcaec8bfaf983e0386de7f7cca1"
    )


def test_new_polities_use_only_neutral_objects_outside_locked_territory():
    objects = generate_arm_objects()
    _locked_base, _locked_clusters, locked_ownership = (
        load_locked_frontier_layout(objects)
    )
    assignments, clusters = allocate_new_frontier_polities(
        objects,
        locked_ownership,
        locked_ownership,
    )

    assert len(FRONTIER_POLITIES) == 77
    assert len(NEW_FRONTIER_POLITIES) == 28
    assert len(assignments) == 28 * 22
    assert not assignments.keys() & locked_ownership.keys()
    assert sum(
        polity.bloc == "miradin"
        for polity in NEW_FRONTIER_POLITIES
    ) == 14
    assert sum(
        polity.bloc == "raih"
        for polity in NEW_FRONTIER_POLITIES
    ) == 14
    locked_intrusions = assign_objects_inside_territories(
        objects,
        locked_ownership,
        [],
    )
    assert not assignments.keys() & locked_intrusions.keys()

    by_id = {obj.id: obj for obj in objects}
    locked_objects = [
        by_id[object_id] for object_id in locked_ownership
    ]
    adjacent_objects = list(locked_objects)
    current_group = None
    for polity in NEW_FRONTIER_POLITIES:
        group = (polity.arm, polity.side)
        if group != current_group:
            adjacent_objects = list(locked_objects)
            current_group = group
        cluster = clusters[polity.stem]
        assert Counter(obj.kind for obj in cluster) == {
            "star": 20,
            "black_hole": 1,
            "junction": 1,
        }
        assert {obj.arm for obj in cluster} == {polity.arm}
        assert all(obj.x * polity.side > 0 for obj in cluster)
        center_x = sum(obj.x for obj in cluster) / len(cluster)
        center_y = sum(obj.y for obj in cluster) / len(cluster)
        assert max(
            hypot(obj.x - center_x, obj.y - center_y)
            for obj in cluster
        ) < 0.25
        assert min(
            hypot(obj.x - old.x, obj.y - old.y)
            for obj in cluster
            for old in adjacent_objects
        ) < 0.20
        adjacent_objects.extend(cluster)

    combined = {**locked_ownership, **assignments}
    additions = {
        object_id: stem
        for object_id, stem in assign_objects_inside_territories(
            objects,
            combined,
            [],
        ).items()
        if stem in NEW_FRONTIER_STEMS
        and by_id[object_id].arm == NEW_FRONTIER_ARM_BY_STEM[stem]
    }
    assert additions
    assert not additions.keys() & locked_ownership.keys()
    assert set(additions.values()) <= NEW_FRONTIER_STEMS


def test_all_assigned_stars_receive_canonical_names_and_planets():
    objects = generate_arm_objects()
    _locked_base, locked_clusters, locked_ownership = (
        load_locked_frontier_layout(objects)
    )
    _new_ownership, new_clusters = allocate_new_frontier_polities(
        objects,
        locked_ownership,
        locked_ownership,
    )
    clusters = {**locked_clusters, **new_clusters}
    catalog = map_canonical_frontier_catalog(clusters)

    stars = [entry for entry in catalog.values() if entry["kind"] == "star"]
    assert len(stars) == 77 * 20
    assert all(entry["token"] for entry in stars)
    assert all(entry["nameEn"] and entry["nameRu"] for entry in stars)
    assert all(entry.get("worlds") is not None for entry in stars)

    for polity in FRONTIER_POLITIES:
        mapped_stars = [
            catalog[obj.id]
            for obj in clusters[polity.stem]
            if obj.kind == "star"
        ]
        assert len(mapped_stars) == 20
        assert all(entry["nameEn"] and entry["nameRu"] for entry in mapped_stars)
        if polity.stem in NEW_FRONTIER_STEMS:
            assert all(entry.get("worlds") for entry in mapped_stars)
        else:
            assert sum(len(entry["worlds"]) for entry in mapped_stars) >= 20


def test_additional_named_frontier_stars_receive_planets():
    star = next(obj for obj in generate_arm_objects() if obj.kind == "star")
    catalog = _generated_claim_catalog(star, "Khelar_Union")

    assert catalog["worlds"] == []

    catalog = _ensure_frontier_star_worlds(star, catalog)

    assert 1 <= len(catalog["worlds"]) <= 3
    assert all(world["token"] for world in catalog["worlds"])
    assert all(world["nameEn"] and world["nameRu"] for world in catalog["worlds"])
