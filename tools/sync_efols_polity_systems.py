# -*- coding: utf-8 -*-
"""Sync polity system lists in EfolsMiradinsPact from live Galaxy API ownership."""

from __future__ import annotations

import argparse
import re
import sys
from collections import defaultdict
from pathlib import Path

import requests

CANON = Path(r"D:\GitHub\EfolsMiradinsPact")
GALAXY_API = "https://galaxyapi.baxic.ru/api/v1/galaxy"
CATALOG_SERVICE = Path(__file__).resolve().parents[1] / "server" / "services" / "catalog-service"

sys.path.insert(0, str(CANON / "tools"))
sys.path.insert(0, str(CATALOG_SERVICE))
from _gen_states_planets import EN_TO_RU  # noqa: E402
from app.service.frontier_naming import (  # noqa: E402
    natural_frontier_black_hole_name,
    natural_frontier_junction_name,
    natural_frontier_star_name,
)

TITLE_RE = re.compile(r"(?m)^#\s+(.+?)\s*/\s*(.+?)\s*$")
WORLD_LINK_RE = re.compile(
    r"\[`([^`]+)`\]\(([^)]+/STATES/EN/[^/]+/worlds/[^)]+\.md)\)"
)
SECTOR_RE = re.compile(
    r"- Sector:\s*\[`([^`]+)`\]\(([^)]+)\)\s*\(`([^`]+)`\)"
)
SUBJECT_EN_RE = re.compile(
    r"(Subject star systems:\s*\*\*)(\d+)(\*\*)",
    re.I,
)
SUBJECT_EN_ALT_RE = re.compile(
    r"(Subject star systems\s*/\s*worlds:\s*\*\*)(\d+)(\*\*\s*/\s*\*\*\d+\*\*)",
    re.I,
)
SUBJECT_RU_RE = re.compile(
    r"(Подвластных звёздных систем:\s*\*\*)(\d+)(\*\*)",
    re.I,
)
SUBJECT_RU_ALT_RE = re.compile(
    r"(Звёздных систем\s*/\s*миров:\s*\*\*)(\d+)(\*\*\s*/\s*\*\*\d+\*\*)",
    re.I,
)
SUBJECT_RU_ALT2_RE = re.compile(
    r"(Подвластных звёздных систем\s*/\s*миров:\s*\*\*)(\d+)(\*\*\s*/\s*\*\*\d+\*\*)",
    re.I,
)


def card_path(system: dict) -> Path | None:
    canon = system.get("canonicalStem") or system.get("stem")
    token = system.get("token")
    kind = system.get("kind")
    if not canon or not token or not kind:
        return None
    if kind == "star":
        return CANON / "UNIVERSE" / "GALAXY" / "STARS" / "EN" / canon / "stars" / f"{token}.md"
    if kind == "black_hole":
        return CANON / "UNIVERSE" / "GALAXY" / "BLACK_HOLES" / "EN" / canon / f"{token}.md"
    if kind == "junction":
        return CANON / "UNIVERSE" / "GALAXY" / "JUNCTIONS" / "EN" / canon / f"{token}.md"
    return None


def ru_card_path(system: dict, ru_canon: str) -> Path | None:
    token = system.get("token")
    kind = system.get("kind")
    if not ru_canon or not token or not kind:
        return None
    if kind == "star":
        return (
            CANON
            / "UNIVERSE"
            / "GALAXY"
            / "STARS"
            / "RU"
            / ru_canon
            / "звёзды"
            / f"{token}.md"
        )
    if kind == "black_hole":
        return CANON / "UNIVERSE" / "GALAXY" / "BLACK_HOLES" / "RU" / ru_canon / f"{token}.md"
    if kind == "junction":
        return CANON / "UNIVERSE" / "GALAXY" / "JUNCTIONS" / "RU" / ru_canon / f"{token}.md"
    return None


def parse_star_card(path: Path) -> tuple[str, str, list[tuple[str, str]]]:
    text = path.read_text(encoding="utf-8") if path.is_file() else ""
    match = TITLE_RE.search(text)
    name_en = match.group(1).strip() if match else path.stem
    name_ru = match.group(2).strip() if match else name_en
    worlds: list[tuple[str, str]] = []
    seen: set[str] = set()
    for wm in WORLD_LINK_RE.finditer(text):
        key = wm.group(2)
        if key in seen:
            continue
        seen.add(key)
        worlds.append((wm.group(1), wm.group(2)))
    return name_en, name_ru, worlds


def parse_named_card(path: Path, fallback: str) -> tuple[str, str, str, str]:
    text = path.read_text(encoding="utf-8") if path.is_file() else ""
    match = TITLE_RE.search(text)
    name_en = match.group(1).strip() if match else fallback
    name_ru = match.group(2).strip() if match else fallback
    sector_en = "—"
    sector_href = ""
    sm = SECTOR_RE.search(text)
    if sm:
        sector_en = sm.group(1)
        sector_href = sm.group(2)
    return name_en, name_ru, sector_en, sector_href


def star_href(owner: str, canon: str, token: str) -> str:
    if owner == canon:
        return f"stars/{token}.md"
    return f"../{canon}/stars/{token}.md"


def hole_href(owner: str, canon: str, token: str) -> str:
    if owner == canon:
        return f"{token}.md"
    return f"../{canon}/{token}.md"


def sector_href_from_card(owner: str, canon: str, card_sector_href: str) -> str:
    if not card_sector_href:
        return ""
    # Card-relative sector links look like ../../../../SECTORS/EN/{canon}/Foo.md
    # From BLACK_HOLES/EN/{owner}/{owner}.md we want ../../../SECTORS/EN/{canon}/Foo.md
    name = Path(card_sector_href).name
    return f"../../../SECTORS/EN/{canon}/{name}"


def world_cell(owner: str, worlds: list[tuple[str, str]]) -> str:
    if not worlds:
        return "—"
    parts = []
    for name, href in worlds:
        # href is relative from star card; rewrite toward STATES from index.
        # Star card uses ../../../../../../STATES/EN/...
        # Index STARS/EN/{owner}/{owner}.md needs ../../../../../STATES/EN/...
        m = re.search(r"STATES/EN/([^/]+)/worlds/([^)]+\.md)", href)
        if not m:
            parts.append(f"`{name}`")
            continue
        parts.append(
            f"[`{name}`](../../../../../STATES/EN/{m.group(1)}/worlds/{m.group(2)})"
        )
    return ", ".join(parts)


def build_star_index(stem: str, systems: list[dict], world_total: int | None) -> str:
    rows = []
    for i, system in enumerate(systems, 1):
        canon = system.get("canonicalStem") or system["stem"]
        path = card_path(system)
        name_en, _name_ru, worlds = parse_star_card(path) if path else (
            system.get("nameEn") or system["token"],
            system.get("nameRu") or system["token"],
            [],
        )
        if system.get("nameEn"):
            name_en = system["nameEn"]
        href = star_href(stem, canon, system["token"])
        star_cell = (
            f"[`{name_en}`]({href})"
            if path and path.is_file()
            else f"`{name_en}`"
        )
        rows.append(
            f"| {i} | {star_cell} | {world_cell(stem, worlds)} |"
        )
    n = len(systems)
    worlds_note = f" Named worlds: **{world_total}**." if world_total is not None else ""
    return (
        f"# {stem} — host stars\n\n"
        f"Subject star systems in `STATES`: **{n}**. Listed host-star systems here: **{n}**."
        f"{worlds_note} One world is not necessarily one star.\n\n"
        f"Membership follows live Galaxy API ownership (`stem`). "
        f"Cards may remain under their catalog folder (`canonicalStem`) when ownership differs.\n\n"
        f"Planet registry: [`STATES/EN/{stem}/{stem}.md`](../../../../../STATES/EN/{stem}/{stem}.md). "
        f"Disk sectors: [`SECTORS/EN/{stem}/{stem}.md`](../../../SECTORS/EN/{stem}/{stem}.md). "
        f"Hypercorridors: [`hypercorridors.md`](hypercorridors.md). "
        f"Black holes: [`BLACK_HOLES/EN/{stem}/{stem}.md`](../../../BLACK_HOLES/EN/{stem}/{stem}.md). "
        f"Junctions: [`JUNCTIONS/EN/{stem}/{stem}.md`](../../../JUNCTIONS/EN/{stem}/{stem}.md).\n\n"
        f"| # | Star | Worlds |\n|---|------|--------|\n"
        + "\n".join(rows)
        + "\n"
    )


def build_star_index_ru(
    stem: str, ru_stem: str, systems: list[dict], world_total: int | None
) -> str:
    rows = []
    for i, system in enumerate(systems, 1):
        canon = system.get("canonicalStem") or system["stem"]
        ru_canon = EN_TO_RU.get(canon, canon)
        path = card_path(system)
        name_en, name_ru, worlds = parse_star_card(path) if path else (
            system.get("nameEn") or system["token"],
            system.get("nameRu") or system["token"],
            [],
        )
        if system.get("nameRu"):
            name_ru = system["nameRu"]
        if ru_stem == ru_canon:
            href = f"звёзды/{system['token']}.md"
        else:
            href = f"../{ru_canon}/звёзды/{system['token']}.md"
        ru_path = ru_card_path(system, ru_canon)
        star_cell = (
            f"[`{name_ru}`]({href})"
            if ru_path and ru_path.is_file()
            else f"`{name_ru}`"
        )
        world_parts = []
        for name, href_w in worlds:
            m = re.search(r"STATES/EN/([^/]+)/worlds/([^)]+\.md)", href_w)
            if not m:
                world_parts.append(f"`{name}`")
                continue
            en_pol = m.group(1)
            ru_pol = EN_TO_RU.get(en_pol, en_pol)
            world_parts.append(
                f"[`{name}`](../../../../../STATES/RU/{ru_pol}/миры/{m.group(2)})"
            )
        world_cell_s = ", ".join(world_parts) if world_parts else "—"
        rows.append(f"| {i} | {star_cell} | {world_cell_s} |")
    n = len(systems)
    worlds_note = f" Именованных миров: **{world_total}**." if world_total is not None else ""
    return (
        f"# {ru_stem} — звёзды-хозяева\n\n"
        f"Подвластных звёздных систем в `STATES`: **{n}**. Listed здесь: **{n}**."
        f"{worlds_note}\n\n"
        f"Состав по живому Galaxy API (`stem`). "
        f"Карточки могут оставаться в каталожной папке (`canonicalStem`).\n\n"
        f"Реестр планет: [`STATES/RU/{ru_stem}/{ru_stem}.md`](../../../../../STATES/RU/{ru_stem}/{ru_stem}.md). "
        f"Секторы: [`SECTORS/RU/{ru_stem}/{ru_stem}.md`](../../../SECTORS/RU/{ru_stem}/{ru_stem}.md). "
        f"Гиперкоридоры: [`гиперкоридоры.md`](гиперкоридоры.md). "
        f"Чёрные дыры: [`BLACK_HOLES/RU/{ru_stem}/{ru_stem}.md`](../../../BLACK_HOLES/RU/{ru_stem}/{ru_stem}.md). "
        f"Стыки: [`JUNCTIONS/RU/{ru_stem}/{ru_stem}.md`](../../../JUNCTIONS/RU/{ru_stem}/{ru_stem}.md).\n\n"
        f"| # | Звезда | Миры |\n|---|--------|------|\n"
        + "\n".join(rows)
        + "\n"
    )


def build_hole_index(stem: str, systems: list[dict]) -> str:
    rows = []
    for i, system in enumerate(systems, 1):
        canon = system.get("canonicalStem") or system["stem"]
        path = card_path(system)
        name_en, _nr, sector_en, sector_href = parse_named_card(
            path, system.get("nameEn") or system["token"]
        )
        if system.get("nameEn"):
            name_en = system["nameEn"]
        href = hole_href(stem, canon, system["token"])
        hole_cell = (
            f"[`{name_en}`]({href})"
            if path and path.is_file()
            else f"`{name_en}`"
        )
        if sector_href:
            sec = f"[`{sector_en}`]({sector_href_from_card(stem, canon, sector_href)})"
        else:
            sec = sector_en
        rows.append(f"| {i} | {hole_cell} | `{system['token']}` | {sec} |")
    n = len(systems)
    return (
        f"# {stem} — black holes\n\n"
        f"Named **black-hole systems** of this polity: **{n}**. "
        f"Membership follows live Galaxy API ownership (`stem`).\n\n"
        f"Host stars: [`STARS/EN/{stem}/{stem}.md`](../../../STARS/EN/{stem}/{stem}.md). "
        f"Junctions: [`JUNCTIONS/EN/{stem}/{stem}.md`](../../../JUNCTIONS/EN/{stem}/{stem}.md). "
        f"Disk sectors: [`SECTORS/EN/{stem}/{stem}.md`](../../../SECTORS/EN/{stem}/{stem}.md).\n\n"
        f"| # | Black hole | Token | Sector |\n|---|------------|-------|--------|\n"
        + "\n".join(rows)
        + "\n"
    )


def build_junction_index(stem: str, systems: list[dict]) -> str:
    rows = []
    for i, system in enumerate(systems, 1):
        canon = system.get("canonicalStem") or system["stem"]
        path = card_path(system)
        name_en, _nr, sector_en, sector_href = parse_named_card(
            path, system.get("nameEn") or system["token"]
        )
        if system.get("nameEn"):
            name_en = system["nameEn"]
        href = hole_href(stem, canon, system["token"])
        junction_cell = (
            f"[`{name_en}`]({href})"
            if path and path.is_file()
            else f"`{name_en}`"
        )
        if sector_href:
            sec = f"[`{sector_en}`]({sector_href_from_card(stem, canon, sector_href)})"
        else:
            sec = sector_en
        rows.append(f"| {i} | {junction_cell} | `{system['token']}` | {sec} |")
    n = len(systems)
    return (
        f"# {stem} — hypercorridor junctions\n\n"
        f"Named **junction systems** of this polity: **{n}**. "
        f"Membership follows live Galaxy API ownership (`stem`).\n\n"
        f"Host stars: [`STARS/EN/{stem}/{stem}.md`](../../../STARS/EN/{stem}/{stem}.md). "
        f"Black holes: [`BLACK_HOLES/EN/{stem}/{stem}.md`](../../../BLACK_HOLES/EN/{stem}/{stem}.md). "
        f"Disk sectors: [`SECTORS/EN/{stem}/{stem}.md`](../../../SECTORS/EN/{stem}/{stem}.md).\n\n"
        f"| # | Junction | Token | Sector |\n|---|----------|-------|--------|\n"
        + "\n".join(rows)
        + "\n"
    )


def build_hole_index_ru(stem: str, ru_stem: str, systems: list[dict]) -> str:
    rows = []
    for i, system in enumerate(systems, 1):
        canon = system.get("canonicalStem") or system["stem"]
        ru_canon = EN_TO_RU.get(canon, canon)
        path = card_path(system)
        _ne, name_ru, sector_en, sector_href = parse_named_card(
            path, system.get("nameRu") or system["token"]
        )
        if system.get("nameRu"):
            name_ru = system["nameRu"]
        if ru_stem == ru_canon:
            href = f"{system['token']}.md"
        else:
            href = f"../{ru_canon}/{system['token']}.md"
        ru_path = ru_card_path(system, ru_canon)
        hole_cell = (
            f"[`{name_ru}`]({href})"
            if ru_path and ru_path.is_file()
            else f"`{name_ru}`"
        )
        if sector_href:
            name = Path(sector_href).name
            sec = f"[`{sector_en}`](../../../SECTORS/RU/{ru_canon}/{name})"
        else:
            sec = sector_en
        rows.append(f"| {i} | {hole_cell} | `{system['token']}` | {sec} |")
    n = len(systems)
    return (
        f"# {ru_stem} — чёрные дыры\n\n"
        f"Именованных систем-чёрных дыр этой державы: **{n}**. "
        f"Состав по живому Galaxy API (`stem`).\n\n"
        f"Звёзды: [`STARS/RU/{ru_stem}/{ru_stem}.md`](../../../STARS/RU/{ru_stem}/{ru_stem}.md). "
        f"Стыки: [`JUNCTIONS/RU/{ru_stem}/{ru_stem}.md`](../../../JUNCTIONS/RU/{ru_stem}/{ru_stem}.md). "
        f"Секторы: [`SECTORS/RU/{ru_stem}/{ru_stem}.md`](../../../SECTORS/RU/{ru_stem}/{ru_stem}.md).\n\n"
        f"| # | Чёрная дыра | Token | Сектор |\n|---|-------------|---------|--------|\n"
        + "\n".join(rows)
        + "\n"
    )


def build_junction_index_ru(stem: str, ru_stem: str, systems: list[dict]) -> str:
    rows = []
    for i, system in enumerate(systems, 1):
        canon = system.get("canonicalStem") or system["stem"]
        ru_canon = EN_TO_RU.get(canon, canon)
        path = card_path(system)
        _ne, name_ru, sector_en, sector_href = parse_named_card(
            path, system.get("nameRu") or system["token"]
        )
        if system.get("nameRu"):
            name_ru = system["nameRu"]
        if ru_stem == ru_canon:
            href = f"{system['token']}.md"
        else:
            href = f"../{ru_canon}/{system['token']}.md"
        ru_path = ru_card_path(system, ru_canon)
        junction_cell = (
            f"[`{name_ru}`]({href})"
            if ru_path and ru_path.is_file()
            else f"`{name_ru}`"
        )
        if sector_href:
            name = Path(sector_href).name
            sec = f"[`{sector_en}`](../../../SECTORS/RU/{ru_canon}/{name})"
        else:
            sec = sector_en
        rows.append(f"| {i} | {junction_cell} | `{system['token']}` | {sec} |")
    n = len(systems)
    return (
        f"# {ru_stem} — стыки гиперкоридоров\n\n"
        f"Именованных стыков этой державы: **{n}**. "
        f"Состав по живому Galaxy API (`stem`).\n\n"
        f"Звёзды: [`STARS/RU/{ru_stem}/{ru_stem}.md`](../../../STARS/RU/{ru_stem}/{ru_stem}.md). "
        f"Чёрные дыры: [`BLACK_HOLES/RU/{ru_stem}/{ru_stem}.md`](../../../BLACK_HOLES/RU/{ru_stem}/{ru_stem}.md). "
        f"Секторы: [`SECTORS/RU/{ru_stem}/{ru_stem}.md`](../../../SECTORS/RU/{ru_stem}/{ru_stem}.md).\n\n"
        f"| # | Стык | Token | Сектор |\n|---|------|---------|--------|\n"
        + "\n".join(rows)
        + "\n"
    )


def patch_subject_count(path: Path, n_stars: int) -> bool:
    if not path.is_file():
        return False
    text = path.read_text(encoding="utf-8")
    updated = text
    for pattern in (
        SUBJECT_EN_RE,
        SUBJECT_EN_ALT_RE,
        SUBJECT_RU_RE,
        SUBJECT_RU_ALT_RE,
        SUBJECT_RU_ALT2_RE,
    ):
        if pattern.search(updated):
            updated = pattern.sub(
                lambda m: f"{m.group(1)}{n_stars}{m.group(3)}",
                updated,
                count=1,
            )
            break
    if updated == text:
        return False
    path.write_text(updated, encoding="utf-8")
    return True


def sort_key(system: dict) -> tuple:
    return (
        (system.get("nameEn") or system.get("token") or "").lower(),
        system.get("token") or "",
    )


def ensure_frontier_name(system: dict) -> dict:
    """Fill names omitted by the API for already-owned generated arm objects."""
    if (
        not str(system.get("id") or "").startswith("frontier:")
        or (
            system.get("token")
            and system.get("nameEn")
            and system.get("nameRu")
        )
    ):
        return system

    naming = {
        "star": natural_frontier_star_name,
        "black_hole": natural_frontier_black_hole_name,
        "junction": natural_frontier_junction_name,
    }.get(system.get("kind"))
    if naming is None:
        return system

    token, name_en, name_ru = naming(system["id"])
    return {
        **system,
        "token": system.get("token") or token,
        "nameEn": system.get("nameEn") or name_en,
        "nameRu": system.get("nameRu") or name_ru,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--apply", action="store_true")
    parser.add_argument(
        "--stem",
        action="append",
        default=[],
        help="Only update the selected polity stem (repeatable)",
    )
    args = parser.parse_args()

    galaxy = requests.get(GALAXY_API, timeout=60).json()
    by_owner: dict[str, dict[str, list[dict]]] = defaultdict(
        lambda: {"star": [], "black_hole": [], "junction": []}
    )
    for raw_system in galaxy.get("systems", []):
        system = ensure_frontier_name(raw_system)
        stem = system.get("stem")
        kind = system.get("kind")
        if not stem or kind not in ("star", "black_hole", "junction"):
            continue
        by_owner[stem][kind].append(system)
    if args.stem:
        selected = set(args.stem)
        by_owner = defaultdict(
            lambda: {"star": [], "black_hole": [], "junction": []},
            {
                stem: groups
                for stem, groups in by_owner.items()
                if stem in selected
            },
        )

    # Derive world totals from canonical cards so newly materialized frontier
    # planets are included without relying on a stale index summary.
    world_totals: dict[str, int] = {}
    for stem in by_owner:
        worlds_dir = CANON / "STATES" / "EN" / stem / "worlds"
        if worlds_dir.is_dir():
            world_totals[stem] = sum(
                1 for _path in worlds_dir.glob("*.md")
            )

    written = 0
    patched = 0
    for stem, groups in sorted(by_owner.items()):
        for kind in groups:
            groups[kind].sort(key=sort_key)
        ru_stem = EN_TO_RU.get(stem)
        star_index = build_star_index(stem, groups["star"], world_totals.get(stem))
        hole_index = build_hole_index(stem, groups["black_hole"])
        junc_index = build_junction_index(stem, groups["junction"])

        targets = [
            (
                CANON / "UNIVERSE" / "GALAXY" / "STARS" / "EN" / stem / f"{stem}.md",
                star_index,
            ),
            (
                CANON
                / "UNIVERSE"
                / "GALAXY"
                / "BLACK_HOLES"
                / "EN"
                / stem
                / f"{stem}.md",
                hole_index,
            ),
            (
                CANON
                / "UNIVERSE"
                / "GALAXY"
                / "JUNCTIONS"
                / "EN"
                / stem
                / f"{stem}.md",
                junc_index,
            ),
        ]
        if ru_stem:
            targets.extend(
                [
                    (
                        CANON
                        / "UNIVERSE"
                        / "GALAXY"
                        / "STARS"
                        / "RU"
                        / ru_stem
                        / f"{ru_stem}.md",
                        build_star_index_ru(
                            stem, ru_stem, groups["star"], world_totals.get(stem)
                        ),
                    ),
                    (
                        CANON
                        / "UNIVERSE"
                        / "GALAXY"
                        / "BLACK_HOLES"
                        / "RU"
                        / ru_stem
                        / f"{ru_stem}.md",
                        build_hole_index_ru(stem, ru_stem, groups["black_hole"]),
                    ),
                    (
                        CANON
                        / "UNIVERSE"
                        / "GALAXY"
                        / "JUNCTIONS"
                        / "RU"
                        / ru_stem
                        / f"{ru_stem}.md",
                        build_junction_index_ru(stem, ru_stem, groups["junction"]),
                    ),
                ]
            )

        for path, content in targets:
            if not path.parent.is_dir():
                print(f"SKIP missing dir {path.parent}")
                continue
            old = path.read_text(encoding="utf-8") if path.is_file() else ""
            if old == content:
                continue
            written += 1
            if args.apply:
                path.write_text(content, encoding="utf-8")

        state_en = CANON / "STATES" / "EN" / stem / f"{stem}.md"
        if args.apply:
            if patch_subject_count(state_en, len(groups["star"])):
                patched += 1
        elif state_en.is_file():
            text = state_en.read_text(encoding="utf-8")
            if SUBJECT_EN_RE.search(text) or SUBJECT_EN_ALT_RE.search(text):
                # count as would-patch if number differs
                m = SUBJECT_EN_RE.search(text) or SUBJECT_EN_ALT_RE.search(text)
                if m and int(m.group(2)) != len(groups["star"]):
                    patched += 1
        if ru_stem:
            state_ru = CANON / "STATES" / "RU" / ru_stem / f"{ru_stem}.md"
            if args.apply:
                if patch_subject_count(state_ru, len(groups["star"])):
                    patched += 1
            elif state_ru.is_file():
                text = state_ru.read_text(encoding="utf-8")
                m = (
                    SUBJECT_RU_RE.search(text)
                    or SUBJECT_RU_ALT_RE.search(text)
                    or SUBJECT_RU_ALT2_RE.search(text)
                )
                if m and int(m.group(2)) != len(groups["star"]):
                    patched += 1

        print(
            f"{stem}: stars={len(groups['star'])} "
            f"holes={len(groups['black_hole'])} "
            f"junctions={len(groups['junction'])}"
        )

    mode = "Updated" if args.apply else "Would update"
    print(f"{mode} {written} index files; {patched} STATE subject-system counts")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
