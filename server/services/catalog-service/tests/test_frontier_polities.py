from collections import Counter
from math import hypot

from app.service.frontier_polities import (
    FRONTIER_POLITIES,
    allocate_frontier_polities,
    assign_objects_inside_territories,
    map_canonical_frontier_catalog,
)
from app.service.spiral_geometry import generate_arm_objects


def test_new_polities_receive_compact_single_arm_pockets():
    objects = generate_arm_objects()
    assignments, clusters = allocate_frontier_polities(objects)

    assert len(FRONTIER_POLITIES) == 21
    assert len(assignments) == 21 * 22
    assert sum(polity.bloc == "miradin" for polity in FRONTIER_POLITIES) == 11
    assert sum(polity.bloc == "raih" for polity in FRONTIER_POLITIES) == 10

    centers = []
    for polity in FRONTIER_POLITIES:
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
        polity.stem for polity in FRONTIER_POLITIES
    }


def test_all_assigned_stars_receive_canonical_names_and_planets():
    objects = generate_arm_objects()
    _, clusters = allocate_frontier_polities(objects)
    catalog = map_canonical_frontier_catalog(clusters)

    stars = [entry for entry in catalog.values() if entry["kind"] == "star"]
    assert len(stars) == 21 * 20
    assert all(entry["token"] for entry in stars)
    assert all(entry["nameEn"] and entry["nameRu"] for entry in stars)
    assert sum(len(entry["worlds"]) for entry in stars) == 21 * 24

    for polity in FRONTIER_POLITIES:
        mapped_stars = [
            catalog[obj.id]
            for obj in clusters[polity.stem]
            if obj.kind == "star"
        ]
        assert len(mapped_stars) == 20
        assert sum(len(entry["worlds"]) for entry in mapped_stars) == 24
