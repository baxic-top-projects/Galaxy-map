"""Give duplicate canonical worlds distinct names in EfolsMiradinsPact docs."""

from __future__ import annotations

import argparse
import re
from pathlib import Path

import requests


CANON = Path(r"D:\GitHub\EfolsMiradinsPact")
GALAXY_API = "http://galaxyapi.baxic.ru/api/v1/galaxy"
PREFIXES = [
    ("Ael", "Аэль"), ("Ar", "Ар"), ("Bel", "Бел"), ("Cael", "Каэль"),
    ("Dra", "Дра"), ("Eri", "Эри"), ("Fen", "Фен"), ("Gal", "Гал"),
    ("Iri", "Ири"), ("Ka", "Ка"), ("Lor", "Лор"), ("Mer", "Мер"),
    ("Nai", "Наи"), ("Or", "Ор"), ("Phae", "Фэй"), ("Qua", "Ква"),
    ("Rhy", "Ри"), ("Sel", "Сел"), ("Tal", "Тал"), ("Vey", "Вей"),
]
MIDDLES = [
    ("dor", "дор"), ("lan", "лан"), ("mir", "мир"), ("nor", "нор"),
    ("ras", "рас"), ("the", "те"), ("val", "вал"), ("xen", "ксен"),
    ("yor", "йор"), ("zen", "зен"), ("cal", "кал"), ("fir", "фир"),
    ("gol", "гол"), ("hel", "хел"), ("jor", "жор"), ("kel", "кел"),
    ("lum", "лум"), ("mor", "мор"), ("ryl", "рил"), ("syl", "сил"),
]
SUFFIXES = [
    ("a", "а"), ("ae", "ай"), ("an", "ан"), ("ara", "ара"),
    ("ea", "ея"), ("el", "эль"), ("en", "ен"), ("ia", "ия"),
    ("ion", "ион"), ("is", "ис"), ("on", "он"), ("ora", "ора"),
    ("os", "ос"), ("um", "ум"), ("une", "ун"), ("yx", "икс"),
    ("aris", "арис"), ("eron", "ерон"), ("iel", "иэль"), ("oris", "орис"),
]


def hash32(value: str) -> int:
    result = 0x811C9DC5
    for char in value:
        result ^= ord(char)
        result = (result * 0x01000193) & 0xFFFFFFFF
    return result


def mint(key: str, used_en: set[str], used_ru: set[str]) -> tuple[str, str]:
    for attempt in range(128):
        value = hash32(f"{key}:{attempt}")
        prefix = PREFIXES[value % len(PREFIXES)]
        value //= len(PREFIXES)
        middle = MIDDLES[value % len(MIDDLES)]
        value //= len(MIDDLES)
        suffix = SUFFIXES[value % len(SUFFIXES)]
        name_en = prefix[0] + middle[0] + suffix[0]
        name_ru = prefix[1] + middle[1] + suffix[1]
        if name_en.casefold() not in used_en and name_ru.casefold() not in used_ru:
            return name_en, name_ru
    raise RuntimeError(f"Unable to mint a unique name for {key}")


def replacements() -> list[dict]:
    galaxy = requests.get(GALAXY_API, timeout=60).json()
    used_en: set[str] = set()
    used_ru: set[str] = set()
    changes = []
    for entry in galaxy.get("search", []):
        if entry.get("kind") != "world":
            continue
        old_en = entry.get("nameEn") or entry.get("token") or "World"
        old_ru = entry.get("nameRu") or entry.get("token") or "Мир"
        new_en, new_ru = old_en, old_ru
        if old_en.casefold() in used_en or old_ru.casefold() in used_ru:
            key = f"{entry['id']}\0{entry.get('token') or ''}"
            new_en, new_ru = mint(key, used_en, used_ru)
            changes.append({**entry, "oldEn": old_en, "oldRu": old_ru, "newEn": new_en, "newRu": new_ru})
        used_en.add(new_en.casefold())
        used_ru.add(new_ru.casefold())
    return changes


def update_star_card(path: Path, change: dict) -> bool:
    if not path.is_file():
        return False
    text = path.read_text(encoding="utf-8")
    updated = text.replace(f"[`{change['oldEn']}`](", f"[`{change['newEn']}`](")
    updated = updated.replace(f" / {change['oldRu']}.", f" / {change['newRu']}.")
    updated = updated.replace(f" | {change['oldRu']} |", f" | {change['newRu']} |")
    if updated == text:
        return False
    path.write_text(updated, encoding="utf-8")
    return True


def update_world_card(path: Path, change: dict) -> bool:
    if not path.is_file():
        return False
    text = path.read_text(encoding="utf-8")
    updated, count = re.subn(
        rf"(?m)^#\s+{re.escape(change['oldEn'])}\s*/\s*{re.escape(change['oldRu'])}\s*$",
        f"# {change['newEn']} / {change['newRu']}",
        text,
        count=1,
    )
    if not count:
        return False
    path.write_text(updated, encoding="utf-8")
    return True


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    changes = replacements()
    star_matches = world_matches = 0
    missing_stars = []
    for change in changes:
        stem, system_token = change["id"].split(":", 1)
        star_path = CANON / "UNIVERSE" / "GALAXY" / "STARS" / "EN" / stem / "stars" / f"{system_token}.md"
        world_path = CANON / "STATES" / "EN" / stem / "worlds" / f"{change['token']}.md"
        if args.apply:
            star_matches += int(update_star_card(star_path, change))
            world_matches += int(update_world_card(world_path, change))
        else:
            star_matches += int(star_path.is_file())
            world_matches += int(world_path.is_file())
        if not star_path.is_file():
            missing_stars.append(str(star_path))
    mode = "Updated" if args.apply else "Would update"
    print(
        f"{mode} {len(changes)} duplicate worlds: "
        f"{star_matches} star cards, {world_matches} world cards; "
        f"{len(missing_stars)} missing star cards"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
