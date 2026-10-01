from __future__ import annotations

import json
import math
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Iterable

from app.service.spiral_geometry import ArmObject

STARS_PER_POLITY = 20
BLACK_HOLES_PER_POLITY = 1
JUNCTIONS_PER_POLITY = 1
LEGACY_CLAIM_RADIUS = 0.034
FRONTIER_CLAIM_MIN = 0.07
FRONTIER_CLAIM_MAX = 0.17
TERRITORY_RASTER_SIZE = 1200
TERRITORY_MAP_LIMIT = 2.8
MARKER_CAPTURE_PIXELS = 4


@dataclass(frozen=True)
class FrontierPolity:
    stem: str
    name_en: str
    name_ru: str
    bloc: str
    color: str
    arm: int

    @property
    def side(self) -> int:
        return 1 if self.bloc == "miradin" else -1

    def payload(self) -> dict:
        return {
            "stem": self.stem,
            "nameEn": self.name_en,
            "nameRu": self.name_ru,
            "bloc": self.bloc,
            "kind": "vassal",
            "color": self.color,
            "label": self.name_ru,
        }


_MIRADIN = (
    ("Caldris_Compact", "Caldris Compact", "Калдрисский Компакт", "#8f4fa8"),
    ("Veyran_Accord", "Veyran Accord", "Вейранский Аккорд", "#a1478f"),
    ("Ossirian_Mandate", "Ossirian Mandate", "Оссирийский Мандат", "#7f5cc9"),
    ("Talaris_Communion", "Talaris Communion", "Таларисская Коммуния", "#b24f75"),
    ("Nivor_Protectorate", "Nivor Protectorate", "Ниворский Протекторат", "#6c69c8"),
    ("Pyralis_Directorate", "Pyralis Directorate", "Пиралисская Директория", "#9b5bb7"),
    ("Ilyr_Assembly", "Ilyr Assembly", "Илирская Ассамблея", "#7651a3"),
    ("Ceryn_League", "Ceryn League", "Церинская Лига", "#c05a9a"),
    ("Damar_Covenant", "Damar Covenant", "Дамарский Ковенант", "#6755b5"),
    ("Khelar_Union", "Khelar Union", "Хеларский Союз", "#a65d87"),
    ("Serrin_Cordon", "Serrin Cordon", "Серринский Кордон", "#805aa8"),
)

_RAIH = (
    ("Auric_Charter", "Auric Charter", "Аурикская Хартия", "#b08a36"),
    ("Dravorn_Dominion", "Dravorn Dominion", "Драворнский Доминион", "#8b9a3d"),
    ("Selqari_Synod", "Selqari Synod", "Селкарийский Синод", "#b46f32"),
    ("Vhalian_Caravanate", "Vhalian Caravanate", "Вхалийский Караванат", "#a19b45"),
    ("Kharad_March", "Kharad March", "Харадский Марш", "#768f3c"),
    (
        "Ortheon_Guild_Republic",
        "Ortheon Guild Republic",
        "Ортеонская Гильдейская Республика",
        "#c0903c",
    ),
    (
        "Yssarian_Concordat",
        "Yssarian Concordat",
        "Иссарийский Конкордат",
        "#8b7b32",
    ),
    ("Brumal_Crown", "Brumal Crown", "Брумальная Корона", "#a66f38"),
    ("Lumenar_Chamber", "Lumenar Chamber", "Люменарская Палата", "#719451"),
    ("Theros_Compact", "Theros Compact", "Теросский Компакт", "#b78646"),
)

FRONTIER_POLITIES = tuple(
    FrontierPolity(row[0], row[1], row[2], "miradin", row[3], arm=1 if index < 6 else 4)
    for index, row in enumerate(_MIRADIN)
) + tuple(
    FrontierPolity(row[0], row[1], row[2], "raih", row[3], arm=2 if index < 5 else 3)
    for index, row in enumerate(_RAIH)
)

_CATALOG_PATH = (
    Path(__file__).resolve().parents[1]
    / "data"
    / "frontier_polity_catalog.json"
)


def allocate_frontier_polities(
    objects: list[ArmObject],
) -> tuple[dict[str, str], dict[str, tuple[ArmObject, ...]]]:
    """Allocate compact one-arm clusters next to the old disk.

    Miradin uses right-side objects in arms 1/4; Raih uses left-side objects in
    arms 2/3. Evenly spaced target points along the old disk rim keep polity
    pockets compact, distinct, and directly adjacent to existing territory.
    """

    object_indexes = {obj.id: index for index, obj in enumerate(objects)}
    available = {obj.id: obj for obj in objects}
    assignments: dict[str, str] = {}
    clusters: dict[str, tuple[ArmObject, ...]] = {}
    bloc_indexes = {"miradin": 0, "raih": 0}
    bloc_totals = {
        "miradin": sum(polity.bloc == "miradin" for polity in FRONTIER_POLITIES),
        "raih": sum(polity.bloc == "raih" for polity in FRONTIER_POLITIES),
    }
    def update_object(obj: ArmObject) -> None:
        objects[object_indexes[obj.id]] = obj
        available[obj.id] = obj

    for polity in FRONTIER_POLITIES:
        position = bloc_indexes[polity.bloc]
        bloc_indexes[polity.bloc] += 1
        fraction = (position + 0.5) / bloc_totals[polity.bloc]
        target_angle = (
            math.pi / 2 - fraction * math.pi
            if polity.bloc == "miradin"
            else math.pi / 2 + fraction * math.pi
        )
        target_x = math.cos(target_angle) * 1.04
        target_y = math.sin(target_angle) * 1.04

        candidates = [
            obj
            for obj in available.values()
            if obj.arm == polity.arm and obj.x * polity.side > 0
        ]
        star_candidates = sorted(
            (obj for obj in candidates if obj.kind == "star"),
            key=lambda obj: (
                math.hypot(obj.x - target_x, obj.y - target_y),
                obj.ordinal,
                obj.id,
            ),
        )
        if not star_candidates:
            raise RuntimeError(f"No stars available for {polity.stem}")
        selected_stars = star_candidates[:STARS_PER_POLITY]
        if len(selected_stars) != STARS_PER_POLITY:
            raise RuntimeError(f"Not enough stars available for {polity.stem}")

        # Keep the generator's irregular positions. Repacking onto a synthetic
        # spiral makes every polity look like an artificial star clump.
        stars = sorted(selected_stars, key=lambda obj: (obj.ordinal, obj.id))

        anchor_x = sum(obj.x for obj in stars) / len(stars)
        anchor_y = sum(obj.y for obj in stars) / len(stars)
        cluster_radius = max(
            math.hypot(obj.x - anchor_x, obj.y - anchor_y)
            for obj in stars
        )

        def take_special(kind: str, offset_index: int) -> ArmObject:
            specials = [obj for obj in candidates if obj.kind == kind]
            if not specials:
                specials = [
                    obj
                    for obj in available.values()
                    if obj.arm == polity.arm and obj.kind == kind
                ]
            if not specials:
                raise RuntimeError(f"No {kind} available for {polity.stem}")
            selected = min(
                specials,
                key=lambda obj: (
                    math.hypot(obj.x - anchor_x, obj.y - anchor_y),
                    obj.ordinal,
                    obj.id,
                ),
            )
            distance = math.hypot(selected.x - anchor_x, selected.y - anchor_y)
            if distance <= max(0.08, cluster_radius * 1.2):
                return selected

            # Reuse an unclaimed special object from this arm and place it
            # inside the new polity pocket. arm_edges() runs after allocation
            # and rebuilds local corridors around its new position.
            offset_angle = (
                (len(clusters) * 2 + offset_index) * 2.399963229728653
            )
            relocated = replace(
                selected,
                x=round(anchor_x + math.cos(offset_angle) * 0.008, 6),
                y=round(anchor_y + math.sin(offset_angle) * 0.008, 6),
            )
            update_object(relocated)
            return relocated

        black_hole = take_special("black_hole", 0)
        junction = take_special("junction", 1)

        cluster = tuple([*stars, black_hole, junction])
        for obj in cluster:
            assignments[obj.id] = polity.stem
            available.pop(obj.id)
        clusters[polity.stem] = cluster

    return assignments, clusters


def assign_objects_inside_territories(
    objects: list[ArmObject],
    assignments: dict[str, str],
    existing_hosts: Iterable[object],
) -> dict[str, str]:
    """Assign currently unclaimed objects already covered by polity fill.

    The calculation uses only the original polity hosts, so assigning objects
    does not recursively expand a territory and consume an entire arm.
    """
    hosts: list[tuple[float, float, str, float]] = []
    assigned_by_stem: dict[str, list[ArmObject]] = {}
    by_id = {obj.id: obj for obj in objects}
    for object_id, stem in assignments.items():
        assigned_by_stem.setdefault(stem, []).append(by_id[object_id])

    claim_by_stem: dict[str, float] = {}
    for stem, systems in assigned_by_stem.items():
        widest_nearest_gap = 0.0
        for system in systems:
            nearest_gap = min(
                (
                    math.hypot(system.x - other.x, system.y - other.y)
                    for other in systems
                    if other.id != system.id
                ),
                default=0.0,
            )
            widest_nearest_gap = max(widest_nearest_gap, nearest_gap)
        claim_by_stem[stem] = min(
            FRONTIER_CLAIM_MAX,
            max(
                FRONTIER_CLAIM_MIN,
                widest_nearest_gap * 0.58 + 0.012,
            ),
        )
        hosts.extend(
            (system.x, system.y, stem, claim_by_stem[stem])
            for system in systems
        )

    for row in existing_hosts:
        if (
            getattr(row, "id", "").startswith("frontier:")
            or not getattr(row, "stem", None)
            or getattr(row, "kind", None)
            not in {"star", "black_hole", "junction"}
        ):
            continue
        hosts.append(
            (
                float(getattr(row, "x")),
                float(getattr(row, "y")),
                str(getattr(row, "stem")),
                LEGACY_CLAIM_RADIUS,
            )
        )

    cell_size = 0.06
    cells: dict[tuple[int, int], list[tuple[float, float, str, float]]] = {}
    for host in hosts:
        key = (
            math.floor(host[0] / cell_size),
            math.floor(host[1] / cell_size),
        )
        cells.setdefault(key, []).append(host)

    additions: dict[str, str] = {}
    pixel_size = 2 * TERRITORY_MAP_LIMIT / TERRITORY_RASTER_SIZE
    marker_radius = MARKER_CAPTURE_PIXELS * pixel_size
    search_cells = math.ceil(
        (FRONTIER_CLAIM_MAX + marker_radius) / cell_size
    )
    sample_offsets = (
        (0.0, 0.0),
        (-marker_radius, 0.0),
        (marker_radius, 0.0),
        (0.0, -marker_radius),
        (0.0, marker_radius),
        (-marker_radius, -marker_radius),
        (-marker_radius, marker_radius),
        (marker_radius, -marker_radius),
        (marker_radius, marker_radius),
    )
    for obj in objects:
        if obj.id in assignments:
            continue
        cell_x = math.floor(obj.x / cell_size)
        cell_y = math.floor(obj.y / cell_size)
        candidates = [
            host
            for dx in range(-search_cells, search_cells + 1)
            for dy in range(-search_cells, search_cells + 1)
            for host in cells.get((cell_x + dx, cell_y + dy), ())
        ]
        pixel_x = math.floor(
            (obj.x + TERRITORY_MAP_LIMIT)
            / (2 * TERRITORY_MAP_LIMIT)
            * TERRITORY_RASTER_SIZE
        )
        pixel_y = math.floor(
            (TERRITORY_MAP_LIMIT - obj.y)
            / (2 * TERRITORY_MAP_LIMIT)
            * TERRITORY_RASTER_SIZE
        )
        sample_x = (
            (pixel_x + 0.5)
            / TERRITORY_RASTER_SIZE
            * 2
            * TERRITORY_MAP_LIMIT
            - TERRITORY_MAP_LIMIT
        )
        sample_y = (
            TERRITORY_MAP_LIMIT
            - (pixel_y + 0.5)
            / TERRITORY_RASTER_SIZE
            * 2
            * TERRITORY_MAP_LIMIT
        )
        coverage: dict[str, tuple[int, float]] = {}
        for offset_x, offset_y in sample_offsets:
            x = sample_x + offset_x
            y = sample_y + offset_y
            valid = [
                (math.hypot(x - host_x, y - host_y), stem)
                for host_x, host_y, stem, claim_radius in candidates
                if math.hypot(x - host_x, y - host_y) <= claim_radius
            ]
            if not valid:
                continue
            distance, stem = min(valid, key=lambda item: (item[0], item[1]))
            count, closest = coverage.get(stem, (0, math.inf))
            coverage[stem] = (count + 1, min(closest, distance))
        if coverage:
            additions[obj.id] = min(
                coverage,
                key=lambda stem: (
                    -coverage[stem][0],
                    coverage[stem][1],
                    stem,
                ),
            )

    return additions


def map_canonical_frontier_catalog(
    clusters: dict[str, tuple[ArmObject, ...]],
) -> dict[str, dict]:
    """Map Efols canonical stars/details onto the selected map objects."""
    if not _CATALOG_PATH.is_file():
        raise RuntimeError(f"Missing frontier catalog: {_CATALOG_PATH}")
    catalog = json.loads(_CATALOG_PATH.read_text(encoding="utf-8"))
    mapped: dict[str, dict] = {}

    for polity in FRONTIER_POLITIES:
        cluster = clusters[polity.stem]
        entries = catalog.get(polity.stem) or []
        for kind in ("star", "black_hole", "junction"):
            objects_of_kind = sorted(
                (obj for obj in cluster if obj.kind == kind),
                key=lambda obj: (obj.ordinal, obj.id),
            )
            entries_of_kind = sorted(
                (entry for entry in entries if entry.get("kind") == kind),
                key=lambda entry: entry.get("token") or "",
            )
            for obj, entry in zip(objects_of_kind, entries_of_kind):
                mapped[obj.id] = entry

        mapped_stars = sum(
            obj.id in mapped for obj in cluster if obj.kind == "star"
        )
        if mapped_stars != STARS_PER_POLITY:
            raise RuntimeError(
                f"{polity.stem}: mapped {mapped_stars}/{STARS_PER_POLITY} stars"
            )

    return mapped
