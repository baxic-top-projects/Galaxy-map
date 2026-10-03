import hashlib
import re
from collections import Counter
from math import hypot

from app.service.frontier_polities import (
    FRONTIER_POLITIES,
    LOCKED_FRONTIER_POLITIES,
    NEW_FRONTIER_ARM_BY_STEM,
    NEW_FRONTIER_POLITIES,
    NEW_FRONTIER_SIDE_BY_STEM,
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


def test_locked_layout_preserves_current_one_hundred_fifty_five_polities():
    objects = generate_arm_objects()
    locked_base, locked_clusters, locked_ownership = (
        load_locked_frontier_layout(objects)
    )

    assert len(LOCKED_FRONTIER_POLITIES) == 155
    assert len(ORIGINAL_FRONTIER_POLITIES) == 21
    assert len(PREVIOUS_FRONTIER_POLITIES) == 28
    assert set(locked_clusters) == {
        polity.stem for polity in LOCKED_FRONTIER_POLITIES
    }
    assert len(locked_base) >= 155
    assert len(locked_ownership) >= 155
    assert all("star-extra" not in object_id for object_id in locked_ownership)
    fingerprint = "\n".join(
        f"{object_id}={stem}"
        for object_id, stem in sorted(locked_ownership.items())
    )
    assert hashlib.sha256(fingerprint.encode()).hexdigest() == (
        "7bfce1b35ac034192b347ea0712c1f472258c4710e7aa3a28e06f37788f744fd"
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

    from app.service.frontier_polities import NEW_FRONTIER_STARS_BY_STEM

    assert len(FRONTIER_POLITIES) == 205
    assert len(NEW_FRONTIER_POLITIES) == 50
    assert sum(NEW_FRONTIER_STARS_BY_STEM.values()) == 90
    assert not assignments.keys() & locked_ownership.keys()
    assert sum(
        polity.bloc == "miradin"
        for polity in NEW_FRONTIER_POLITIES
    ) == 25
    assert sum(
        polity.bloc == "raih"
        for polity in NEW_FRONTIER_POLITIES
    ) == 25
    assert all(
        "star-extra" not in object_id for object_id in assignments
    )
    assert sum(
        1 for oid in assignments if ":star-" in oid or oid.count("star")
    ) >= 90

    by_id = {obj.id: obj for obj in objects}
    for polity in NEW_FRONTIER_POLITIES:
        cluster = clusters[polity.stem]
        stars = [obj for obj in cluster if obj.kind == "star"]
        assert len(stars) == NEW_FRONTIER_STARS_BY_STEM[polity.stem]
        assert all("star-extra" not in obj.id for obj in stars)

    combined = {**locked_ownership, **assignments}
    additions = {
        object_id: stem
        for object_id, stem in assign_objects_inside_territories(
            objects,
            combined,
            [],
        ).items()
        if stem in NEW_FRONTIER_STEMS
        and by_id[object_id].x * NEW_FRONTIER_SIDE_BY_STEM[stem] > 0
    }
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
    assert len(stars) >= 155
    assert all(entry["token"] for entry in stars)
    assert all(entry["nameEn"] and entry["nameRu"] for entry in stars)
    assert all(entry.get("worlds") is not None for entry in stars)
    assert all(
        not re.fullmatch(r"Star[0-9a-fA-F]{6,}", entry["token"] or "")
        and not re.fullmatch(r"Star[0-9a-fA-F]{6,}", entry["nameEn"] or "")
        for entry in stars
    )

    from app.service.frontier_polities import NEW_FRONTIER_STARS_BY_STEM

    for polity in FRONTIER_POLITIES:
        mapped_stars = [
            catalog[obj.id]
            for obj in clusters[polity.stem]
            if obj.kind == "star"
        ]
        expected = NEW_FRONTIER_STARS_BY_STEM.get(polity.stem)
        if expected is not None:
            assert len(mapped_stars) == expected
        else:
            assert len(mapped_stars) >= 1
        assert all(entry["nameEn"] and entry["nameRu"] for entry in mapped_stars)
        if polity.stem in NEW_FRONTIER_STEMS:
            assert all(entry.get("worlds") for entry in mapped_stars)


def test_additional_named_frontier_stars_receive_planets():
    star = next(obj for obj in generate_arm_objects() if obj.kind == "star")
    catalog = _generated_claim_catalog(star, "Khelar_Union")

    assert catalog["worlds"] == []

    catalog = _ensure_frontier_star_worlds(star, catalog)

    assert 1 <= len(catalog["worlds"]) <= 3
    assert all(world["token"] for world in catalog["worlds"])
    assert all(world["nameEn"] and world["nameRu"] for world in catalog["worlds"])
