"""Materialize manually claimed frontier stars and worlds in EfolsMiradinsPact."""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parents[1]
CANON = ROOT.parent / "EfolsMiradinsPact"
CATALOG_SERVICE = ROOT / "server" / "services" / "catalog-service"
GALAXY_API = "https://galaxyapi.baxic.ru/api/v1"

sys.path.insert(0, str(CANON / "tools"))
sys.path.insert(0, str(CATALOG_SERVICE))

from _gen_states_planets import EN_TO_RU  # noqa: E402

PLANET_TYPES_RU = {
    "arid": "Засушливый",
    "continental": "Континентальный",
    "ocean": "Океанический",
    "savanna": "Саванна",
    "tropical": "Тропический",
}


def _write(path: Path, content: str, apply: bool) -> bool:
    if path.is_file():
        return False
    if apply:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
    return True


def _star_card(system: dict, *, ru: bool) -> str:
    stem = system["stem"]
    ru_stem = EN_TO_RU[stem]
    worlds = system["worlds"]
    if ru:
        rows = "\n".join(
            f"| {index} | [`{world['nameRu']}`]"
            f"(../../../../../../STATES/RU/{ru_stem}/миры/{world['token']}.md)"
            f" | `{world['token']}` | {world['planetType']} |"
            for index, world in enumerate(worlds, 1)
        )
        return (
            f"# {system['nameRu']} / {system['nameEn']}\n\n"
            "## Планеты\n"
            f"- Держава: [{ru_stem}](../../../../../../STATES/RU/{ru_stem}/{ru_stem}.md)\n\n"
            "| № | Планета | Токен | Тип |\n"
            "|---|---------|-------|-----|\n"
            f"{rows}\n\n"
            "## Статус\n"
            f"- Токен: `{system['token']}`\n"
            "- Роль: звезда подвластной приграничной системы\n"
            f"- Тип звезды: {system['starType']}\n"
            f"- Рукав: {system['frontierArm']}\n"
            f"- ID карты: `{system['id']}`\n"
        )

    rows = "\n".join(
        f"| {index} | [`{world['token']}`]"
        f"(../../../../../../STATES/EN/{stem}/worlds/{world['token']}.md)"
        f" | {world['nameRu']} | {world['planetType']} |"
        for index, world in enumerate(worlds, 1)
    )
    return (
        f"# {system['nameEn']} / {system['nameRu']}\n\n"
        "## Planets\n"
        f"- Polity: [{stem}](../../../../../../STATES/EN/{stem}/{stem}.md)\n\n"
        "| # | Planet | RU | Type |\n"
        "|---|--------|----|------|\n"
        f"{rows}\n\n"
        "## Status\n"
        f"- Token: `{system['token']}`\n"
        "- Role: subject frontier host star\n"
        f"- Star type: {system['starType']}\n"
        f"- Frontier arm: {system['frontierArm']}\n"
        f"- Galaxy map ID: `{system['id']}`\n"
    )


def _world_card(system: dict, world: dict, *, ru: bool) -> str:
    stem = system["stem"]
    ru_stem = EN_TO_RU[stem]
    if ru:
        planet_type = PLANET_TYPES_RU.get(
            world["planetTypeKey"],
            world["planetType"],
        )
        return (
            f"# {world['nameRu']} / {world['nameEn']}\n\n"
            "## Статус\n"
            f"- Держава: [{ru_stem}](../{ru_stem}.md)\n"
            "- Роль: приграничный мир\n"
            f"- Тип планеты: {planet_type} (`{world['planetTypeKey']}`)\n"
            f"- Звезда: [`{system['nameRu']}`]"
            f"(../../../../UNIVERSE/GALAXY/STARS/RU/{ru_stem}/звёзды/{system['token']}.md)"
            f" (`{system['token']}`)\n"
            f"- ID карты звезды: `{system['id']}`\n"
        )
    return (
        f"# {world['nameEn']} / {world['nameRu']}\n\n"
        "## Status\n"
        f"- Polity: [{stem}](../{stem}.md)\n"
        "- Role: frontier world\n"
        f"- Planet type: {world['planetType']}\n"
        f"- Host star: [`{system['nameEn']}`]"
        f"(../../../../UNIVERSE/GALAXY/STARS/EN/{stem}/stars/{system['token']}.md)"
        f" (`{system['token']}`)\n"
        f"- Galaxy map star ID: `{system['id']}`\n"
    )


def _patch_world_registry(path: Path, worlds: list[dict], *, ru: bool) -> bool:
    if not path.is_file():
        return False
    text = path.read_text(encoding="utf-8")
    heading = "## Планеты (реестр миров)" if ru else "## Worlds (planet registry)"
    start = text.find(heading)
    if start < 0:
        return False
    end = text.find("\n## ", start + len(heading))
    if end < 0:
        end = len(text)
    section = text[start:end]
    existing_tokens = set(re.findall(r"\]\((?:worlds|миры)/([^)]+)\.md\)", section))
    additions = [world for world in worlds if world["token"] not in existing_tokens]
    if not additions:
        return False

    row_matches = list(re.finditer(r"(?m)^\|\s*(\d+)\s*\|.*$", section))
    if not row_matches:
        raise RuntimeError(f"World registry table is missing in {path}")
    number = max(int(match.group(1)) for match in row_matches)
    rows = []
    for world in additions:
        number += 1
        label = world["nameRu"] if ru else world["nameEn"]
        folder = "миры" if ru else "worlds"
        role = "приграничный мир" if ru else "frontier world"
        rows.append(
            f"| {number} | [`{label}`]({folder}/{world['token']}.md) | {role} |"
        )
    insert_at = start + row_matches[-1].end()
    updated = text[:insert_at] + "\n" + "\n".join(rows) + text[insert_at:]
    total = number
    if ru:
        updated = re.sub(
            r"(подвластных миров:\s*\*\*)\d+(\*\*)",
            rf"\g<1>{total}\g<2>",
            updated,
            flags=re.I,
        )
        updated = re.sub(
            r"(Подвластных миров в этом профиле:\s*\*\*)\d+(\*\*)",
            rf"\g<1>{total}\g<2>",
            updated,
        )
    else:
        updated = re.sub(
            r"(subject worlds:\s*\*\*)\d+(\*\*)",
            rf"\g<1>{total}\g<2>",
            updated,
            flags=re.I,
        )
        updated = re.sub(
            r"(Subject worlds in this profile:\s*\*\*)\d+(\*\*)",
            rf"\g<1>{total}\g<2>",
            updated,
        )
    path.write_text(updated, encoding="utf-8")
    return True


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()

    galaxy = requests.get(f"{GALAXY_API}/galaxy", timeout=120).json()
    candidates = [
        system
        for system in galaxy.get("systems", [])
        if system.get("kind") == "star"
        and str(system.get("id") or "").startswith("frontier:")
        and "canonicalStem" in system
        and system.get("canonicalStem") is None
        and system.get("stem") in EN_TO_RU
    ]
    details = [
        requests.get(
            f"{GALAXY_API}/systems/{system['id']}",
            timeout=60,
        ).json()
        for system in candidates
    ]

    created = 0
    by_stem: dict[str, list[dict]] = {}
    for system in details:
        stem = system["stem"]
        ru_stem = EN_TO_RU[stem]
        by_stem.setdefault(stem, []).extend(system["worlds"])
        targets = (
            (
                CANON / "UNIVERSE" / "GALAXY" / "STARS" / "EN"
                / stem / "stars" / f"{system['token']}.md",
                _star_card(system, ru=False),
            ),
            (
                CANON / "UNIVERSE" / "GALAXY" / "STARS" / "RU"
                / ru_stem / "звёзды" / f"{system['token']}.md",
                _star_card(system, ru=True),
            ),
        )
        created += sum(_write(path, content, args.apply) for path, content in targets)
        for world in system["worlds"]:
            world_targets = (
                (
                    CANON / "STATES" / "EN" / stem / "worlds"
                    / f"{world['token']}.md",
                    _world_card(system, world, ru=False),
                ),
                (
                    CANON / "STATES" / "RU" / ru_stem / "миры"
                    / f"{world['token']}.md",
                    _world_card(system, world, ru=True),
                ),
            )
            created += sum(
                _write(path, content, args.apply)
                for path, content in world_targets
            )

    patched = 0
    if args.apply:
        for stem, worlds in by_stem.items():
            ru_stem = EN_TO_RU[stem]
            patched += _patch_world_registry(
                CANON / "STATES" / "EN" / stem / f"{stem}.md",
                worlds,
                ru=False,
            )
            patched += _patch_world_registry(
                CANON / "STATES" / "RU" / ru_stem / f"{ru_stem}.md",
                worlds,
                ru=True,
            )

    mode = "Created" if args.apply else "Would create"
    print(
        f"{mode} {created} cards for {len(details)} manually claimed stars "
        f"and {sum(len(system['worlds']) for system in details)} worlds; "
        f"patched {patched} polity profiles"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
