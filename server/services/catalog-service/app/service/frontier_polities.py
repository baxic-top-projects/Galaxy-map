from __future__ import annotations

import json
import math
from dataclasses import dataclass, replace
from pathlib import Path

from app.service.spiral_geometry import ArmObject

STARS_PER_POLITY = 20
BLACK_HOLES_PER_POLITY = 1
JUNCTIONS_PER_POLITY = 1
NEUTRAL_STAR_CLEARANCE = 0.13
NEUTRAL_STAR_MIN_GALACTIC_RADIUS = 1.10
POLITY_ATTACHMENT_RADIUS = 1.075


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
    cluster_zones: list[tuple[float, float, float]] = []

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
        target_x = math.cos(target_angle) * 1.12
        target_y = math.sin(target_angle) * 1.12

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

        # Move the complete natural pocket toward the legacy disk as one unit.
        # Relative positions stay untouched, while its inner edge now meets the
        # old outer territories instead of leaving a visible empty corridor.
        anchor_radius = math.hypot(anchor_x, anchor_y)
        shift = POLITY_ATTACHMENT_RADIUS - anchor_radius
        shift_x = (anchor_x / anchor_radius) * shift
        shift_y = (anchor_y / anchor_radius) * shift
        cluster = tuple(
            replace(
                obj,
                x=round(obj.x + shift_x, 6),
                y=round(obj.y + shift_y, 6),
            )
            for obj in (*stars, black_hole, junction)
        )
        for obj in cluster:
            update_object(obj)

        moved_stars = [obj for obj in cluster if obj.kind == "star"]
        anchor_x = sum(obj.x for obj in moved_stars) / len(moved_stars)
        anchor_y = sum(obj.y for obj in moved_stars) / len(moved_stars)
        cluster_radius = max(
            math.hypot(obj.x - anchor_x, obj.y - anchor_y)
            for obj in moved_stars
        )
        cluster_zones.append(
            (
                anchor_x,
                anchor_y,
                max(NEUTRAL_STAR_CLEARANCE, cluster_radius + 0.025),
            )
        )
        for obj in cluster:
            assignments[obj.id] = polity.stem
            available.pop(obj.id)
        clusters[polity.stem] = cluster

    # The arm generator already begins directly outside the legacy disk. Only
    # eject unclaimed objects that fall inside a new polity pocket; do not
    # project the whole arm onto a shared radius, which creates a circular row.
    for obj in tuple(available.values()):
        if obj.kind not in {"star", "black_hole", "junction"}:
            continue
        kind_salt = {"star": 17, "black_hole": 43, "junction": 71}[obj.kind]
        phase = (
            (obj.ordinal * 2654435761 + obj.arm * 104729 + kind_salt) % 1009
        ) / 1009
        relocated = obj
        original_radius = math.hypot(obj.x, obj.y)
        inward_influence = max(
            0.0,
            min(1.0, 1.0 - (original_radius - 1.10) / 0.60),
        )
        inward_shift = (0.035 + phase * 0.035) * inward_influence
        minimum_radius = NEUTRAL_STAR_MIN_GALACTIC_RADIUS + phase * 0.02
        moved_radius = max(minimum_radius, original_radius - inward_shift)
        if moved_radius < original_radius:
            original_angle = math.atan2(obj.y, obj.x)
            relocated = replace(
                obj,
                x=round(math.cos(original_angle) * moved_radius, 6),
                y=round(math.sin(original_angle) * moved_radius, 6),
            )

        # If an object intersects any polity pocket, move it farther out along
        # the arm. Scatter both its radius and angle so displaced systems do
        # not form a dense row immediately outside the polity border.
        for attempt in range(6):
            overlaps = [
                clearance - math.hypot(
                    relocated.x - center_x,
                    relocated.y - center_y,
                )
                for center_x, center_y, clearance in cluster_zones
            ]
            overlap = max(overlaps)
            if overlap <= 0:
                break
            angle = math.atan2(relocated.y, relocated.x)
            angular_phase = (
                phase + attempt * 0.3819660112501051
            ) % 1.0
            angle += (angular_phase - 0.5) * 0.24
            radius = (
                math.hypot(relocated.x, relocated.y)
                + overlap
                + 0.03
                + phase * 0.10
            )
            relocated = replace(
                relocated,
                x=round(math.cos(angle) * radius, 6),
                y=round(math.sin(angle) * radius, 6),
            )
        update_object(relocated)

    return assignments, clusters


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
