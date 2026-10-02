from __future__ import annotations

import hashlib
import re

PLACEHOLDER_STAR_RE = re.compile(r"^Star[0-9a-fA-F]{6,}$")
PLACEHOLDER_STAR_RU_RE = re.compile(r"^Звезда-Star[0-9a-fA-F]{6,}$")

STAR_STEM_EN = (
    "Aeth", "Arion", "Brae", "Cal", "Corv", "Dusk", "Ely", "Fae", "Glim",
    "Haur", "Iri", "Jast", "Kael", "Lum", "Myr", "Nyx", "Orin", "Pyr",
    "Que", "Radi", "Sol", "Thal", "Umb", "Vel", "Vesper", "Xel", "Yl", "Zeph",
)
STAR_STEM_RU = (
    "Эт", "Арион", "Брей", "Кал", "Корв", "Даск", "Эли", "Фей", "Глим",
    "Хаур", "Ири", "Джаст", "Каэл", "Лум", "Мир", "Никс", "Орин", "Пир",
    "Кве", "Ради", "Сол", "Тал", "Умб", "Вел", "Веспер", "Ксел", "Ил", "Зеф",
)
STAR_SUF_EN = (
    "ath", "el", "iris", "ith", "nael", "or", "oth",
    "une", "ulyx", "yx", "ane", "uth", "eos", "del",
)
STAR_SUF_RU = (
    "ат", "эль", "ирис", "ит", "наэль", "ор", "от",
    "ун", "уликс", "икс", "ан", "ут", "эос", "дел",
)
STAR_QUALIFIER_EN = (
    "Altair", "Vega", "Orion", "Lyra", "Draco", "Cygnus", "Aquila",
    "Carina", "Eridan", "Helios", "Lunara", "Nerion", "Solis", "Thalassa",
)
STAR_QUALIFIER_RU = (
    "Альтаир", "Вега", "Орион", "Лира", "Дракон", "Лебедь", "Аквила",
    "Карина", "Эридан", "Гелиос", "Лунара", "Нерион", "Солис", "Таласса",
)
HOLE_ROOT_EN = (
    "Acheron", "Cerberus", "Erebus", "Kharon", "Lethe", "Moirai",
    "Nox", "Orcus", "Styx", "Tartarus", "Umbra", "Vesper",
)
HOLE_ROOT_RU = (
    "Ахерон", "Цербер", "Эреб", "Харон", "Лета", "Мойры",
    "Нокс", "Оркус", "Стикс", "Тартар", "Умбра", "Веспер",
)
HOLE_SUFFIX_EN = (
    "Abyss", "Chasm", "Eclipse", "Maw", "Rift", "Shadow",
    "Singularity", "Veil", "Void", "Well", "Grave", "Horizon",
    "Nexus", "Depth", "Crown",
)
HOLE_SUFFIX_RU = (
    "Бездна", "Провал", "Затмение", "Пасть", "Разлом", "Тень",
    "Сингулярность", "Завеса", "Пустота", "Колодец", "Могила", "Горизонт",
    "Узел", "Глубина", "Корона",
)
JUNCTION_ROOT_EN = (
    "Aurel", "Cael", "Elyr", "Ilyon", "Kael",
    "Lumen", "Orion", "Solis", "Thalen", "Vesper",
)
JUNCTION_ROOT_RU = (
    "Аурель", "Каэль", "Элир", "Илион", "Каэл",
    "Люмен", "Орион", "Солис", "Тален", "Веспер",
)
JUNCTION_SUFFIX_EN = (
    "Arch", "Bridge", "Crossing", "Gate", "Link",
    "Passage", "Span", "Threshold", "Way", "Confluence",
)
JUNCTION_SUFFIX_RU = (
    "Арка", "Мост", "Перекрёсток", "Врата", "Связь",
    "Проход", "Пролёт", "Порог", "Путь", "Слияние",
)
WORLD_ROOT_EN = ("Astra", "Cera", "Doran", "Elya", "Iona", "Kora", "Mira", "Nysa")
WORLD_ROOT_RU = ("Астра", "Цера", "Доран", "Элия", "Иона", "Кора", "Мира", "Ниса")
WORLD_SUFFIX_EN = ("Haven", "Reach", "Vale", "Crown", "Quay", "Ridge")
WORLD_SUFFIX_RU = ("Хейвен", "Рич", "Вейл", "Краун", "Кей", "Ридж")
WORLD_ORDINAL_EN = ("Prime", "Secunda", "Tertia")
WORLD_ORDINAL_RU = ("Прима", "Секунда", "Терция")
WORLD_TYPES = (
    ("continental", "Continental (temperate climate)"),
    ("ocean", "Ocean (ocean climate)"),
    ("tropical", "Tropical (tropical climate)"),
    ("arid", "Arid (arid climate)"),
    ("savanna", "Savanna (savanna climate)"),
    ("tundra", "Tundra (cold climate)"),
)


def _object_index(system_id: str, per_arm: int) -> int:
    parts = system_id.split(":")
    arm = int(parts[1].removeprefix("arm-"))
    ordinal = int(parts[2].rsplit("-", 1)[-1])
    return (arm - 1) * per_arm + ordinal - 1


def is_placeholder_star_label(*labels: str | None) -> bool:
    """True when a token/name is the old Star{hex} / Звезда-Star{hex} fallback."""
    for label in labels:
        if not label:
            continue
        if PLACEHOLDER_STAR_RE.fullmatch(label) or PLACEHOLDER_STAR_RU_RE.fullmatch(
            label
        ):
            return True
    return False


def natural_frontier_star_name(system_id: str) -> tuple[str, str, str]:
    index = _object_index(system_id, 1290)
    base_count = len(STAR_STEM_EN) * len(STAR_SUF_EN)
    base_index = index % base_count
    qualifier_index = index // base_count
    stem_index = base_index % len(STAR_STEM_EN)
    suffix_index = base_index // len(STAR_STEM_EN)
    base_en = f"{STAR_STEM_EN[stem_index]}{STAR_SUF_EN[suffix_index]}"
    base_ru = f"{STAR_STEM_RU[stem_index]}{STAR_SUF_RU[suffix_index]}"
    qualifier_en = STAR_QUALIFIER_EN[qualifier_index % len(STAR_QUALIFIER_EN)]
    qualifier_ru = STAR_QUALIFIER_RU[qualifier_index % len(STAR_QUALIFIER_RU)]
    # Keep tokens unique when the same base+qualifier wraps after many arms.
    wrap = qualifier_index // len(STAR_QUALIFIER_EN)
    if wrap:
        token = f"{base_en}{qualifier_en}{wrap}"
        name_en = f"{base_en} {qualifier_en} {wrap}"
        name_ru = f"{base_ru} {qualifier_ru} {wrap}"
    else:
        token = f"{base_en}{qualifier_en}"
        name_en = f"{base_en} {qualifier_en}"
        name_ru = f"{base_ru} {qualifier_ru}"
    return token, name_en, name_ru


def natural_frontier_black_hole_name(system_id: str) -> tuple[str, str, str]:
    index = _object_index(system_id, 43)
    root_index = index % len(HOLE_ROOT_EN)
    suffix_index = index // len(HOLE_ROOT_EN)
    return (
        f"{HOLE_ROOT_EN[root_index]}{HOLE_SUFFIX_EN[suffix_index]}",
        f"{HOLE_ROOT_EN[root_index]} {HOLE_SUFFIX_EN[suffix_index]}",
        f"{HOLE_SUFFIX_RU[suffix_index]} {HOLE_ROOT_RU[root_index]}",
    )


def natural_frontier_junction_name(system_id: str) -> tuple[str, str, str]:
    index = _object_index(system_id, 25)
    root_index = index % len(JUNCTION_ROOT_EN)
    suffix_index = index // len(JUNCTION_ROOT_EN)
    return (
        f"{JUNCTION_ROOT_EN[root_index]}{JUNCTION_SUFFIX_EN[suffix_index]}",
        f"{JUNCTION_ROOT_EN[root_index]} {JUNCTION_SUFFIX_EN[suffix_index]}",
        f"{JUNCTION_SUFFIX_RU[suffix_index]} {JUNCTION_ROOT_RU[root_index]}",
    )


def generated_frontier_worlds(system_id: str, star_token: str) -> list[dict]:
    digest = hashlib.sha256(f"frontier-worlds:{system_id}".encode("utf-8")).digest()
    worlds = []
    for index in range(1 + digest[0] % 3):
        root_index = digest[1 + index] % len(WORLD_ROOT_EN)
        suffix_index = digest[4 + index] % len(WORLD_SUFFIX_EN)
        type_key, planet_type = WORLD_TYPES[digest[7 + index] % len(WORLD_TYPES)]
        token = (
            f"{star_token[:5]}{WORLD_ROOT_EN[root_index]}"
            f"{WORLD_SUFFIX_EN[suffix_index]}{WORLD_ORDINAL_EN[index]}"
        )
        _token, _name_en, star_name_ru = natural_frontier_star_name(system_id)
        worlds.append(
            {
                "token": token,
                "nameEn": token,
                "nameRu": (
                    f"{star_name_ru} {WORLD_ROOT_RU[root_index]} "
                    f"{WORLD_SUFFIX_RU[suffix_index]} {WORLD_ORDINAL_RU[index]}"
                ),
                "planetType": planet_type,
                "planetTypeKey": type_key,
                "role": "frontier world",
                "satellites": [],
            }
        )
    return worlds
