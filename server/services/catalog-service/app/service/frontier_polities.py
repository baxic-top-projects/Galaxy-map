from __future__ import annotations

import math
from dataclasses import dataclass, replace

from app.service.spiral_geometry import ArmObject

STARS_PER_POLITY = 20
BLACK_HOLES_PER_POLITY = 1
JUNCTIONS_PER_POLITY = 1


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
        stars = star_candidates[:STARS_PER_POLITY]
        if len(stars) != STARS_PER_POLITY:
            raise RuntimeError(f"Not enough stars available for {polity.stem}")

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
            objects[object_indexes[relocated.id]] = relocated
            available[relocated.id] = relocated
            return relocated

        black_hole = take_special("black_hole", 0)
        junction = take_special("junction", 1)

        cluster = tuple([*stars, black_hole, junction])
        for obj in cluster:
            assignments[obj.id] = polity.stem
            available.pop(obj.id)
        clusters[polity.stem] = cluster

    return assignments, clusters
