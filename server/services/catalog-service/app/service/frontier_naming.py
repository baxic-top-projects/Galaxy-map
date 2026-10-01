from __future__ import annotations

import hashlib

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
WORLD_ROOT_EN = ("Astra", "Cera", "Doran", "Elya", "Iona", "Kora", "Mira", "Nysa")
WORLD_ROOT_RU = ("Астра", "Цера", "Доран", "Элия", "Иона", "Кора", "Мира", "Ниса")
WORLD_SUFFIX_EN = ("Haven", "Reach", "Vale", "Crown", "Quay", "Ridge")
WORLD_SUFFIX_RU = ("Хейвен", "Рич", "Вейл", "Краун", "Кей", "Ридж")
WORLD_TYPES = (
    ("continental", "Continental (temperate climate)"),
    ("ocean", "Ocean (ocean climate)"),
    ("tropical", "Tropical (tropical climate)"),
    ("arid", "Arid (arid climate)"),
    ("savanna", "Savanna (savanna climate)"),
    ("tundra", "Tundra (cold climate)"),
)


def natural_frontier_star_name(system_id: str) -> tuple[str, str, str]:
    digest = hashlib.md5(f"frontier-star:{system_id}".encode("utf-8")).hexdigest()
    value = int(digest[:12], 16)
    stem_index = value % len(STAR_STEM_EN)
    suffix_index = (value // 13) % len(STAR_SUF_EN)
    tail = digest[12:18]
    token = f"{STAR_STEM_EN[stem_index]}{STAR_SUF_EN[suffix_index]}{tail}"
    name_ru = f"{STAR_STEM_RU[stem_index]}{STAR_SUF_RU[suffix_index]}{tail}"
    return token, token, name_ru


def generated_frontier_worlds(system_id: str, star_token: str) -> list[dict]:
    digest = hashlib.sha256(f"frontier-worlds:{system_id}".encode("utf-8")).digest()
    worlds = []
    for index in range(1 + digest[0] % 3):
        root_index = digest[1 + index] % len(WORLD_ROOT_EN)
        suffix_index = digest[4 + index] % len(WORLD_SUFFIX_EN)
        type_key, planet_type = WORLD_TYPES[digest[7 + index] % len(WORLD_TYPES)]
        tail = digest[10 + index : 12 + index].hex()
        token = (
            f"{star_token[:5]}{WORLD_ROOT_EN[root_index]}"
            f"{WORLD_SUFFIX_EN[suffix_index]}{tail}"
        )
        worlds.append(
            {
                "token": token,
                "nameEn": token,
                "nameRu": (
                    f"{star_token[:5]}{WORLD_ROOT_RU[root_index]}"
                    f"{WORLD_SUFFIX_RU[suffix_index]}{tail}"
                ),
                "planetType": planet_type,
                "planetTypeKey": type_key,
                "role": "frontier world",
                "satellites": [],
            }
        )
    return worlds
