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

_MIRADIN_BATCH28 = (
    ("Haldor_Compact", "Haldor Compact", "Халдорский Компакт", "#ad4c58"),
    ("Wren_Accord", "Wren Accord", "Вренский Аккорд", "#6b4cad"),
    ("Basalt_Mandate", "Basalt Mandate", "Базальтовый Мандат", "#714cad"),
    ("Grove_Communion", "Grove Communion", "Гроувская Коммуния", "#764cad"),
    ("Frost_Ward", "Frost Ward", "Фростский Дозор", "#7b4cad"),
    ("Ember_Array", "Ember Array", "Эмберский Массив", "#814cad"),
    ("Prism_Assembly", "Prism Assembly", "Призменная Ассамблея", "#864cad"),
    ("Glass_League", "Glass League", "Стеклянная Лига", "#8b4cad"),
    ("Anvil_Covenant", "Anvil Covenant", "Анвильский Ковенант", "#904cad"),
    ("Needle_Union", "Needle Union", "Игольный Союз", "#964cad"),
    ("Tide_Protectorate", "Tide Protectorate", "Приливный Протекторат", "#9b4cad"),
    ("Ash_Directorate", "Ash Directorate", "Пепельная Директория", "#a04cad"),
    ("Quiet_Chamber", "Quiet Chamber", "Тихая Палата", "#a64cad"),
    ("Span_League", "Span League", "Пролётная Лига", "#ad4c87"),
)

_RAIH_BATCH28 = (
    ("Aurin_Charter", "Aurin Charter", "Ауринская Хартия", "#c29c4e"),
    ("Cinder_Dominion", "Cinder Dominion", "Синдерский Доминион", "#c29f4e"),
    ("Choir_Synod", "Choir Synod", "Хоровой Синод", "#c2a24e"),
    ("Silt_Caravanate", "Silt Caravanate", "Силтовый Караванат", "#c2a54e"),
    ("Grit_March", "Grit March", "Гритский Марш", "#c2a74e"),
    (
        "Latch_Guild_Republic",
        "Latch Guild Republic",
        "Затворная Гильдейская Республика",
        "#c2aa4e",
    ),
    ("Bloom_Concordat", "Bloom Concordat", "Цветочный Конкордат", "#c2ad4e"),
    ("Rime_Crown", "Rime Crown", "Инеевая Корона", "#c2af4e"),
    ("Volt_Chamber", "Volt Chamber", "Вольтовая Палата", "#c2b24e"),
    ("Facet_Compact", "Facet Compact", "Гранёный Компакт", "#c2b54e"),
    (
        "Coil_Protectorate",
        "Coil Protectorate",
        "Катушечный Протекторат",
        "#c2b84e",
    ),
    ("Mirror_League", "Mirror League", "Зеркальная Лига", "#c2ba4e"),
    ("Salt_Accord", "Salt Accord", "Соляной Аккорд", "#c2bd4e"),
    ("Hex_Mandate", "Hex Mandate", "Гекс Мандат", "#c27e4e"),
)

_MIRADIN_BATCH29 = (
    ("Quill_Compact", "Quill Compact", "Квилльский Компакт", "#b04d5f"),
    ("Amber_Accord", "Amber Accord", "Амберский Аккорд", "#704cad"),
    ("Flint_Mandate", "Flint Mandate", "Флинтский Мандат", "#754cad"),
    ("Willow_Communion", "Willow Communion", "Виллоуская Коммуния", "#7a4cad"),
    ("Glacier_Ward", "Glacier Ward", "Глейшерский Дозор", "#804cad"),
    ("Spark_Array", "Spark Array", "Спаркский Массив", "#854cad"),
    ("Lens_Assembly", "Lens Assembly", "Ленсская Ассамблея", "#8a4cad"),
    ("Crystal_League", "Crystal League", "Кристальная Лига", "#8f4cad"),
    ("Hammer_Covenant", "Hammer Covenant", "Хаммерский Ковенант", "#944cad"),
    ("Spindle_Union", "Spindle Union", "Спиндельский Союз", "#994cad"),
    ("Harbor_Protectorate", "Harbor Protectorate", "Харборский Протекторат", "#9e4cad"),
    ("Smoke_Directorate", "Smoke Directorate", "Смоукская Директория", "#a34cad"),
    ("Archive_Chamber", "Archive Chamber", "Архивная Палата", "#a84cad"),
    ("Bridge_League", "Bridge League", "Бриджская Лига", "#ad4c7a"),
)

_RAIH_BATCH29 = (
    ("Opal_Charter", "Opal Charter", "Опаловая Хартия", "#c29d4e"),
    ("Slag_Dominion", "Slag Dominion", "Шлаковый Доминион", "#c2a04e"),
    ("Cantor_Synod", "Cantor Synod", "Канторский Синод", "#c2a34e"),
    ("Dune_Caravanate", "Dune Caravanate", "Дюнный Караванат", "#c2a64e"),
    ("Pebble_March", "Pebble March", "Пебблский Марш", "#c2a94e"),
    (
        "Hinge_Guild_Republic",
        "Hinge Guild Republic",
        "Хинджевая Гильдейская Республика",
        "#c2ac4e",
    ),
    ("Petal_Concordat", "Petal Concordat", "Петалский Конкордат", "#c2af4e"),
    ("Hail_Crown", "Hail Crown", "Хейльская Корона", "#c2b24e"),
    ("Ampere_Chamber", "Ampere Chamber", "Амперная Палата", "#c2b54e"),
    ("Gem_Compact", "Gem Compact", "Гемский Компакт", "#c2b84e"),
    (
        "Spring_Protectorate",
        "Spring Protectorate",
        "Спрингский Протекторат",
        "#c2bb4e",
    ),
    ("Reflect_League", "Reflect League", "Рефлектская Лига", "#c2be4e"),
    ("Brine_Accord", "Brine Accord", "Брайновый Аккорд", "#c2c14e"),
    ("Glyph_Mandate", "Glyph Mandate", "Глифский Мандат", "#c2804e"),
)

_MIRADIN_BATCH30 = (
    ("Arc_Array", "Arc Array", "Арковский Массив", "#b04d5f"),
    ("Cobble_Mandate", "Cobble Mandate", "Кобблский Мандат", "#704cad"),
    ("Ironbark_League", "Ironbark League", "Айронбаркская Лига", "#754cad"),
    ("Jetty_Protectorate", "Jetty Protectorate", "Джеттийский Протекторат", "#7a4cad"),
    ("Ledger_Chamber", "Ledger Chamber", "Леджерская Палата", "#804cad"),
    ("Meadow_Accord", "Meadow Accord", "Медоуский Аккорд", "#854cad"),
    ("Myrtle_Communion", "Myrtle Communion", "Миртовая Коммуния", "#8a4cad"),
    ("Parch_Compact", "Parch Compact", "Парчский Компакт", "#8f4cad"),
    ("Pin_Covenant", "Pin Covenant", "Пинский Ковенант", "#944cad"),
    ("Prismglass_Assembly", "Prismglass Assembly", "Призмгласская Ассамблея", "#994cad"),
    ("Rimefall_Ward", "Rimefall Ward", "Римфолльский Дозор", "#9e4cad"),
    ("Scroll_Union", "Scroll Union", "Скролльский Союз", "#a34cad"),
    ("Soot_Directorate", "Soot Directorate", "Сутовая Директория", "#a84cad"),
    ("Spanlink_League", "Spanlink League", "Спанлинкская Лига", "#ad4c7a"),
)

_RAIH_BATCH30 = (
    ("Alkali_Accord", "Alkali Accord", "Алкалийский Аккорд", "#c29d4e"),
    ("Blossom_Concordat", "Blossom Concordat", "Блоссомский Конкордат", "#c2a04e"),
    ("Cascade_Protectorate", "Cascade Protectorate", "Каскадный Протекторат", "#c2a34e"),
    ("Cinderfall_Dominion", "Cinderfall Dominion", "Синдерфолльский Доминион", "#c2a64e"),
    ("Drift_Caravanate", "Drift Caravanate", "Дрифтовый Караванат", "#c2a94e"),
    ("Faraday_Chamber", "Faraday Chamber", "Фарадеевская Палата", "#c2ac4e"),
    ("Hoarfrost_Crown", "Hoarfrost Crown", "Хоарфростская Корона", "#c2af4e"),
    ("Ivory_Charter", "Ivory Charter", "Айвори Хартия", "#c2b24e"),
    ("Jewel_Compact", "Jewel Compact", "Джуэльный Компакт", "#c2b54e"),
    ("Psalm_Synod", "Psalm Synod", "Псалмовый Синод", "#c2b84e"),
    (
        "Rivet_Guild_Republic",
        "Rivet Guild Republic",
        "Риветовая Гильдейская Республика",
        "#c2bb4e",
    ),
    ("Shale_March", "Shale March", "Сланцевый Марш", "#c2be4e"),
    ("Sigil_Mandate", "Sigil Mandate", "Сигильский Мандат", "#c2c14e"),
    ("Specular_League", "Specular League", "Спекулярная Лига", "#c2804e"),
)


def _miradin_polities(
    rows: tuple[tuple[str, str, str, str], ...],
    *,
    first_arm_count: int,
) -> tuple[FrontierPolity, ...]:
    return tuple(
        FrontierPolity(
            row[0],
            row[1],
            row[2],
            "miradin",
            row[3],
            arm=1 if index < first_arm_count else 4,
        )
        for index, row in enumerate(rows)
    )


def _raih_polities(
    rows: tuple[tuple[str, str, str, str], ...],
    *,
    first_arm_count: int,
) -> tuple[FrontierPolity, ...]:
    return tuple(
        FrontierPolity(
            row[0],
            row[1],
            row[2],
            "raih",
            row[3],
            arm=2 if index < first_arm_count else 3,
        )
        for index, row in enumerate(rows)
    )


ORIGINAL_FRONTIER_POLITIES = _miradin_polities(
    _MIRADIN,
    first_arm_count=6,
) + _raih_polities(
    _RAIH,
    first_arm_count=5,
)

PREVIOUS_FRONTIER_POLITIES = _miradin_polities(
    _MIRADIN_BATCH28,
    first_arm_count=7,
) + _raih_polities(
    _RAIH_BATCH28,
    first_arm_count=7,
)

BATCH29_FRONTIER_POLITIES = _miradin_polities(
    _MIRADIN_BATCH29,
    # Arms 1/3 are saturated after the previous wave; keep Miradin on the
    # right by placing the whole batch on arm 4.
    first_arm_count=0,
) + _raih_polities(
    _RAIH_BATCH29,
    # Keep Raih on the left by placing the whole batch on arm 2.
    first_arm_count=14,
)

LOCKED_FRONTIER_POLITIES = (
    ORIGINAL_FRONTIER_POLITIES
    + PREVIOUS_FRONTIER_POLITIES
    + BATCH29_FRONTIER_POLITIES
)

NEW_FRONTIER_POLITIES = _miradin_polities(
    _MIRADIN_BATCH30,
    # Spread Miradin across right-side arms 1 then 4; leave slack on arm 1.
    first_arm_count=4,
) + _raih_polities(
    _RAIH_BATCH30,
    # Spread Raih across left-side arms 2 then 3; arm 3 only has ~98 neutrals.
    first_arm_count=10,
)

NEW_FRONTIER_STEMS = frozenset(
    polity.stem for polity in NEW_FRONTIER_POLITIES
)
NEW_FRONTIER_ARM_BY_STEM = {
    polity.stem: polity.arm for polity in NEW_FRONTIER_POLITIES
}
NEW_FRONTIER_SIDE_BY_STEM = {
    polity.stem: polity.side for polity in NEW_FRONTIER_POLITIES
}
FRONTIER_POLITIES = LOCKED_FRONTIER_POLITIES + NEW_FRONTIER_POLITIES

_CATALOG_PATH = (
    Path(__file__).resolve().parents[1]
    / "data"
    / "frontier_polity_catalog.json"
)
_LAYOUT_LOCK_PATH = (
    Path(__file__).resolve().parents[1]
    / "data"
    / "frontier_layout_lock.json"
)


def load_locked_frontier_layout(
    objects: list[ArmObject],
) -> tuple[
    dict[str, str],
    dict[str, tuple[ArmObject, ...]],
    dict[str, str],
]:
    """Load the immutable ownership/coordinate snapshot for current polities."""
    if not _LAYOUT_LOCK_PATH.is_file():
        raise RuntimeError(f"Missing frontier layout lock: {_LAYOUT_LOCK_PATH}")
    layout = json.loads(_LAYOUT_LOCK_PATH.read_text(encoding="utf-8"))
    expected_polities = [
        polity.stem for polity in LOCKED_FRONTIER_POLITIES
    ]
    if layout.get("polities") != expected_polities:
        raise RuntimeError(
            "Frontier polity definitions differ from the locked layout"
        )

    object_indexes = {obj.id: index for index, obj in enumerate(objects)}
    for object_id, coordinates in layout["coordinates"].items():
        index = object_indexes.get(object_id)
        if index is None:
            raise RuntimeError(
                f"Locked frontier object is missing: {object_id}"
            )
        objects[index] = replace(
            objects[index],
            x=float(coordinates[0]),
            y=float(coordinates[1]),
            z=float(coordinates[2]),
        )

    by_id = {obj.id: obj for obj in objects}
    clusters = {
        stem: tuple(by_id[object_id] for object_id in object_ids)
        for stem, object_ids in layout["clusters"].items()
    }
    return (
        dict(layout["baseOwnership"]),
        clusters,
        dict(layout["ownership"]),
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
        "miradin": sum(
            polity.bloc == "miradin"
            for polity in ORIGINAL_FRONTIER_POLITIES
        ),
        "raih": sum(
            polity.bloc == "raih"
            for polity in ORIGINAL_FRONTIER_POLITIES
        ),
    }
    def update_object(obj: ArmObject) -> None:
        objects[object_indexes[obj.id]] = obj
        available[obj.id] = obj

    for polity in ORIGINAL_FRONTIER_POLITIES:
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
                ordinal=stars[len(stars) // 2].ordinal,
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


def allocate_new_frontier_polities(
    objects: list[ArmObject],
    reserved_ids: Iterable[str],
    boundary_ownership: dict[str, str] | None = None,
    polities: tuple[FrontierPolity, ...] | None = None,
) -> tuple[dict[str, str], dict[str, tuple[ArmObject, ...]]]:
    """Allocate new polities only on neutral objects outside the layout lock."""
    targets = polities or NEW_FRONTIER_POLITIES
    reserved = set(reserved_ids)
    boundary = (
        set(boundary_ownership)
        if boundary_ownership is not None
        else reserved
    )
    # Locked ownership is already a frozen snapshot. Do not also reserve
    # theoretical territory-fill candidates: that starves the next wave on the
    # correct left/right sides. Adjacency still uses the boundary ownership set.
    object_indexes = {obj.id: index for index, obj in enumerate(objects)}
    available = {
        obj.id: obj
        for obj in objects
        if obj.id not in reserved
    }
    assignments: dict[str, str] = {}
    clusters: dict[str, tuple[ArmObject, ...]] = {}
    selected_by_stem: dict[str, list[ArmObject]] = {
        polity.stem: [] for polity in targets
    }
    locked_objects = [
        objects[object_indexes[object_id]]
        for object_id in boundary
        if object_id in object_indexes
    ]
    groups: list[tuple[int, int, list[FrontierPolity]]] = []
    for arm, side in ((1, 1), (4, 1), (2, -1), (3, -1)):
        group = [
            polity
            for polity in targets
            if polity.arm == arm and polity.side == side
        ]
        if group:
            groups.append((arm, side, group))

    # Pick the densest compact neutral pocket nearest the old boundary, remove
    # it, and repeat. Miradin pockets stay on +x; Raih on -x. When a side/arm
    # no longer has 20 stars inside a compact radius, mint the shortfall into
    # the pocket instead of sprawling across distant clumps.
    max_pocket_radius = 0.22

    def mint_star(
        *,
        arm: int,
        side: int,
        center_x: float,
        center_y: float,
        ordinal: int,
        mint_index: int,
    ) -> ArmObject:
        extra_index = sum(
            1 for obj in objects if obj.kind == "star" and "-extra-" in obj.id
        )
        angle = (
            len(LOCKED_FRONTIER_POLITIES) * 2 + mint_index
        ) * 2.399963229728653
        radius = 0.012 + (mint_index % 5) * 0.007
        x = center_x + math.cos(angle) * radius
        y = center_y + math.sin(angle) * radius
        if x * side <= 0:
            x = center_x + side * radius
        minted = ArmObject(
            id=f"frontier:arm-{arm}:star-extra-{extra_index:03d}",
            arm=arm,
            ordinal=ordinal,
            kind="star",
            star_type_key="class_g",
            x=round(x, 6),
            y=round(y, 6),
            z=0.0,
        )
        objects.append(minted)
        object_indexes[minted.id] = len(objects) - 1
        available[minted.id] = minted
        return minted

    for arm, side, group in groups:
        adjacent_objects = list(locked_objects)
        candidates = [
            obj
            for obj in available.values()
            if obj.kind == "star"
            and obj.arm == arm
            and obj.x * side > 0
        ]
        for polity in group:
            if not candidates and not adjacent_objects:
                raise RuntimeError(
                    f"Not enough neutral stars available for {polity.stem}"
                )
            best: tuple[
                float,
                int,
                str,
                list[ArmObject],
            ] | None = None
            for seed in candidates:
                nearest = sorted(
                    candidates,
                    key=lambda obj: (
                        math.hypot(obj.x - seed.x, obj.y - seed.y),
                        obj.ordinal,
                        obj.id,
                    ),
                )
                compact = [
                    obj
                    for obj in nearest
                    if math.hypot(obj.x - seed.x, obj.y - seed.y)
                    <= max_pocket_radius
                ][:STARS_PER_POLITY]
                if len(compact) < 8:
                    compact = nearest[: min(12, len(nearest))]
                if not compact:
                    continue
                center_x = sum(obj.x for obj in compact) / len(compact)
                center_y = sum(obj.y for obj in compact) / len(compact)
                compact_radius = max(
                    math.hypot(obj.x - center_x, obj.y - center_y)
                    for obj in compact
                )
                mint_need = max(0, STARS_PER_POLITY - len(compact))
                boundary_gap = min(
                    (
                        math.hypot(seed.x - old.x, seed.y - old.y)
                        for old in adjacent_objects
                    ),
                    default=0.0,
                )
                candidate = (
                    compact_radius + mint_need * 0.05 + boundary_gap * 0.35,
                    seed.ordinal,
                    seed.id,
                    compact,
                )
                if best is None or candidate[:3] < best[:3]:
                    best = candidate
            if best is None:
                # Side/arm exhausted: seed a new pocket on the polity's side
                # next to the locked boundary and mint the whole cluster.
                anchor = min(
                    (
                        obj
                        for obj in adjacent_objects
                        if obj.arm == arm and obj.x * side > 0
                    ),
                    key=lambda obj: (obj.ordinal, obj.id),
                    default=None,
                )
                if anchor is None:
                    raise RuntimeError(
                        f"Not enough neutral stars available for {polity.stem}"
                    )
                compact = []
                center_x = anchor.x + side * 0.04
                center_y = anchor.y
                best = (0.0, anchor.ordinal, anchor.id, compact)
            assert best is not None
            selected = list(best[3])
            if selected:
                center_x = sum(obj.x for obj in selected) / len(selected)
                center_y = sum(obj.y for obj in selected) / len(selected)
                ordinal = selected[len(selected) // 2].ordinal
            else:
                ordinal = best[1]
            mint_index = 0
            while len(selected) < STARS_PER_POLITY:
                minted = mint_star(
                    arm=arm,
                    side=side,
                    center_x=center_x,
                    center_y=center_y,
                    ordinal=ordinal,
                    mint_index=mint_index,
                )
                selected.append(minted)
                mint_index += 1
            selected_by_stem[polity.stem] = selected
            adjacent_objects.extend(selected)
            selected_ids = {obj.id for obj in selected}
            candidates = [
                obj for obj in candidates if obj.id not in selected_ids
            ]
            for object_id in selected_ids:
                available.pop(object_id, None)

    for polity in targets:
        stars = sorted(
            selected_by_stem[polity.stem],
            key=lambda obj: (obj.ordinal, obj.id),
        )
        anchor_x = sum(obj.x for obj in stars) / len(stars)
        anchor_y = sum(obj.y for obj in stars) / len(stars)
        cluster_radius = max(
            math.hypot(obj.x - anchor_x, obj.y - anchor_y)
            for obj in stars
        )

        def take_special(kind: str, offset_index: int) -> ArmObject:
            # Miradin stays on +x (arms 1/4); Raih on -x (arms 2/3). Never
            # steal a special from the opposite side — mint instead.
            def pocket_xy(angle: float) -> tuple[float, float]:
                radius = 0.008
                x = anchor_x + math.cos(angle) * radius
                y = anchor_y + math.sin(angle) * radius
                if x * polity.side <= 0:
                    x = anchor_x + polity.side * radius
                return round(x, 6), round(y, 6)

            selected = min(
                (
                    obj
                    for obj in available.values()
                    if obj.kind == kind
                    and obj.arm == polity.arm
                    and obj.x * polity.side > 0
                ),
                key=lambda obj: (
                    math.hypot(obj.x - anchor_x, obj.y - anchor_y),
                    obj.ordinal,
                    obj.id,
                ),
                default=None,
            )
            if selected is None:
                extra_index = sum(
                    1
                    for obj in objects
                    if obj.kind == kind and "-extra-" in obj.id
                )
                minted_id = (
                    f"frontier:arm-{polity.arm}:{kind}-extra-{extra_index:03d}"
                )
                offset_angle = (
                    (
                        len(LOCKED_FRONTIER_POLITIES)
                        + len(clusters)
                    )
                    * 2
                    + offset_index
                ) * 2.399963229728653
                minted_x, minted_y = pocket_xy(offset_angle)
                minted = ArmObject(
                    id=minted_id,
                    arm=polity.arm,
                    ordinal=stars[len(stars) // 2].ordinal,
                    kind=kind,
                    star_type_key=(
                        "black_hole" if kind == "black_hole" else "junction"
                    ),
                    x=minted_x,
                    y=minted_y,
                    z=0.0,
                )
                objects.append(minted)
                object_indexes[minted.id] = len(objects) - 1
                available[minted.id] = minted
                return minted
            distance = math.hypot(
                selected.x - anchor_x,
                selected.y - anchor_y,
            )
            if (
                selected.arm == polity.arm
                and selected.x * polity.side > 0
                and distance <= max(0.08, cluster_radius * 1.2)
            ):
                return selected
            offset_angle = (
                (
                    len(LOCKED_FRONTIER_POLITIES)
                    + len(clusters)
                )
                * 2
                + offset_index
            ) * 2.399963229728653
            relocated_x, relocated_y = pocket_xy(offset_angle)
            relocated = replace(
                selected,
                arm=polity.arm,
                x=relocated_x,
                y=relocated_y,
                ordinal=stars[len(stars) // 2].ordinal,
            )
            objects[object_indexes[selected.id]] = relocated
            available[selected.id] = relocated
            return relocated

        cluster = (
            *stars,
            take_special("black_hole", 0),
            take_special("junction", 1),
        )
        for obj in cluster:
            assignments[obj.id] = polity.stem
            available.pop(obj.id, None)
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

    from app.service.frontier_naming import (
        generated_frontier_worlds,
        is_placeholder_star_label,
        natural_frontier_black_hole_name,
        natural_frontier_junction_name,
        natural_frontier_star_name,
    )

    star_type_names = {
        "class_m": "Class M",
        "class_k": "Class K",
        "class_g": "Class G",
        "class_f": "Class F",
        "class_a": "Class A",
        "class_b": "Class B",
        "black_hole": "Black Hole",
        "junction": "Empty hypercorridor node",
    }

    for polity in FRONTIER_POLITIES:
        cluster = clusters.get(polity.stem)
        if cluster is None:
            continue
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
                if obj.kind == "star" and is_placeholder_star_label(
                    entry.get("token"),
                    entry.get("nameEn"),
                    entry.get("nameRu"),
                ):
                    token, name_en, name_ru = natural_frontier_star_name(obj.id)
                    worlds = entry.get("worlds") or []
                    if not worlds:
                        worlds = generated_frontier_worlds(obj.id, token)
                    mapped[obj.id] = {
                        **entry,
                        "token": token,
                        "nameEn": name_en,
                        "nameRu": name_ru,
                        "worlds": worlds,
                    }
                else:
                    mapped[obj.id] = entry
            for obj in objects_of_kind[len(entries_of_kind) :]:
                if obj.kind == "star":
                    token, name_en, name_ru = natural_frontier_star_name(obj.id)
                    worlds = generated_frontier_worlds(obj.id, token)
                elif obj.kind == "black_hole":
                    token, name_en, name_ru = (
                        natural_frontier_black_hole_name(obj.id)
                    )
                    worlds = []
                else:
                    token, name_en, name_ru = (
                        natural_frontier_junction_name(obj.id)
                    )
                    worlds = []
                mapped[obj.id] = {
                    "canonicalId": None,
                    "token": token,
                    "kind": obj.kind,
                    "nameEn": name_en,
                    "nameRu": name_ru,
                    "starType": star_type_names[obj.star_type_key],
                    "starTypeKey": obj.star_type_key,
                    "sectorId": "",
                    "sectorNameEn": "",
                    "worlds": worlds,
                    "uninhabited": [],
                    "features": [],
                    "territoryAnchor": True,
                }

        mapped_stars = sum(
            obj.id in mapped for obj in cluster if obj.kind == "star"
        )
        if mapped_stars != STARS_PER_POLITY:
            raise RuntimeError(
                f"{polity.stem}: mapped {mapped_stars}/{STARS_PER_POLITY} stars"
            )

    return mapped
