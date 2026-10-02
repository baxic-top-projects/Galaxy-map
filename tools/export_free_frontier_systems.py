"""Export remaining free frontier systems from live Galaxy API into EfolsMiradinsPact."""

from __future__ import annotations

import json
import sys
import urllib.request
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CATALOG_SERVICE = ROOT / "server" / "services" / "catalog-service"
CANON = ROOT.parent / "EfolsMiradinsPact"
API = "https://galaxyapi.baxic.ru/api/v1/galaxy"

sys.path.insert(0, str(CATALOG_SERVICE))

from app.service.frontier_naming import (  # noqa: E402
    natural_frontier_black_hole_name,
    natural_frontier_junction_name,
    natural_frontier_star_name,
)

TYPE_EN = {
    "star": "Star",
    "black_hole": "Black hole",
    "junction": "Hypercorridor junction",
}
TYPE_RU = {
    "star": "Звезда",
    "black_hole": "Чёрная дыра",
    "junction": "Стык гиперкоридоров",
}


def _fetch() -> dict:
    request = urllib.request.Request(API, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(request, timeout=120) as response:
        return json.load(response)


def _named(
    system_id: str,
    kind: str,
    token: str,
    name_en: str,
    name_ru: str,
) -> tuple[str, str, str]:
    if token and name_en and name_ru:
        return token, name_en, name_ru
    naming = {
        "star": natural_frontier_star_name,
        "black_hole": natural_frontier_black_hole_name,
        "junction": natural_frontier_junction_name,
    }[kind]
    gen_token, gen_en, gen_ru = naming(system_id)
    return token or gen_token, name_en or gen_en, name_ru or gen_ru


def _document(entries: list[dict], *, ru: bool) -> str:
    counts = Counter(entry["kind"] for entry in entries)
    if ru:
        title = "# Свободные нейтральные системы спиральных рукавов"
        intro = (
            "Реестр объектов рукавов `frontier:*`, у которых на текущей карте "
            "ещё нет владельца. Axis Well и канонические системы вне рукавов "
            "сюда не входят. Пустым объектам даны стабильные имена по ID карты."
        )
        summary = (
            f"Всего: **{len(entries)}**; звёзд: **{counts['star']}**; "
            f"чёрных дыр: **{counts['black_hole']}**; "
            f"стыков: **{counts['junction']}**."
        )
        header = "| № | Токен | Тип | Название | Рукав | ID карты | X | Y |"
        separator = "|---|-------|-----|----------|-------|----------|---|---|"
        rows = [
            f"| {index} | `{entry['token']}` | {TYPE_RU[entry['kind']]} | "
            f"{entry['nameRu']} | {entry['arm']} | `{entry['id']}` | "
            f"{entry['x']:.6f} | {entry['y']:.6f} |"
            for index, entry in enumerate(entries, 1)
        ]
    else:
        title = "# Free neutral spiral-arm systems"
        intro = (
            "Registry of `frontier:*` arm objects that currently have no owner "
            "on the live map. The Axis Well and non-arm canonical systems are "
            "excluded. Blank objects receive stable names derived from map IDs."
        )
        summary = (
            f"Total: **{len(entries)}**; stars: **{counts['star']}**; "
            f"black holes: **{counts['black_hole']}**; "
            f"junctions: **{counts['junction']}**."
        )
        header = "| # | Token | Type | Display name | Arm | Map ID | X | Y |"
        separator = "|---|-------|------|--------------|-----|--------|---|---|"
        rows = [
            f"| {index} | `{entry['token']}` | {TYPE_EN[entry['kind']]} | "
            f"{entry['nameEn']} | {entry['arm']} | `{entry['id']}` | "
            f"{entry['x']:.6f} | {entry['y']:.6f} |"
            for index, entry in enumerate(entries, 1)
        ]
    return "\n".join(
        [title, "", intro, "", summary, "", header, separator, *rows, ""]
    )


def _arm_of(system_id: str) -> int:
    try:
        return int(system_id.split(":")[1].removeprefix("arm-"))
    except (IndexError, ValueError):
        return 0


def main() -> int:
    data = _fetch()
    free = []
    for system in data.get("systems") or []:
        system_id = str(system.get("id") or "")
        if not system_id.startswith("frontier:"):
            continue
        if system.get("stem"):
            continue
        kind = system.get("kind")
        if kind not in TYPE_EN:
            continue
        token, name_en, name_ru = _named(
            system_id,
            kind,
            system.get("token") or "",
            system.get("nameEn") or "",
            system.get("nameRu") or "",
        )
        free.append(
            {
                "id": system_id,
                "token": token,
                "kind": kind,
                "nameEn": name_en,
                "nameRu": name_ru,
                "arm": system.get("arm") or _arm_of(system_id),
                "x": float(system.get("x") or 0.0),
                "y": float(system.get("y") or 0.0),
            }
        )
    free.sort(
        key=lambda entry: (entry["arm"], entry["kind"], entry["token"], entry["id"])
    )
    counts = Counter(entry["kind"] for entry in free)

    en_dir = CANON / "UNIVERSE" / "GALAXY" / "FRONTIER_SYSTEMS" / "EN"
    ru_dir = CANON / "UNIVERSE" / "GALAXY" / "FRONTIER_SYSTEMS" / "RU"
    en_dir.mkdir(parents=True, exist_ok=True)
    ru_dir.mkdir(parents=True, exist_ok=True)
    (en_dir / "Neutral_Free.md").write_text(_document(free, ru=False), encoding="utf-8")
    (ru_dir / "Свободные_нейтральные.md").write_text(
        _document(free, ru=True),
        encoding="utf-8",
    )

    for path, ru in (
        (en_dir / "README.md", False),
        (ru_dir / "README.md", True),
    ):
        if not path.is_file():
            continue
        text = path.read_text(encoding="utf-8")
        if ru:
            block = (
                "## Свободные нейтральные объекты\n\n"
                f"На текущей карте без владельца остаётся **{len(free)}** объектов рукавов: "
                f"звёзд **{counts['star']}**, чёрных дыр **{counts['black_hole']}**, "
                f"стыков **{counts['junction']}**. "
                f"Полный реестр: [Свободные_нейтральные.md](Свободные_нейтральные.md).\n"
            )
            marker = "## Свободные нейтральные объекты"
        else:
            block = (
                "## Free neutral objects\n\n"
                f"The live map still has **{len(free)}** unowned arm objects: "
                f"**{counts['star']}** stars, **{counts['black_hole']}** black holes, "
                f"**{counts['junction']}** junctions. "
                f"Full registry: [Neutral_Free.md](Neutral_Free.md).\n"
            )
            marker = "## Free neutral objects"
        if marker in text:
            before, _rest = text.split(marker, 1)
            rest = _rest.split("\n## ", 1)
            after = ("\n## " + rest[1]) if len(rest) > 1 else ""
            text = before.rstrip() + "\n\n" + block + after
        else:
            text = text.rstrip() + "\n\n" + block
        path.write_text(text, encoding="utf-8")

    galaxy_readme = CANON / "UNIVERSE" / "GALAXY" / "README.md"
    if galaxy_readme.is_file():
        text = galaxy_readme.read_text(encoding="utf-8")
        line = (
            "- `FRONTIER_SYSTEMS/` — дополнительные системы держав на спиральных рукавах; "
            f"свободных нейтральных объектов сейчас **{len(free)}** "
            f"(звёзд {counts['star']}, чёрных дыр {counts['black_hole']}, "
            f"стыков {counts['junction']})"
        )
        if "`FRONTIER_SYSTEMS/`" in text:
            lines = []
            for existing in text.splitlines():
                lines.append(line if "`FRONTIER_SYSTEMS/`" in existing else existing)
            text = "\n".join(lines) + "\n"
        else:
            text = text.rstrip() + "\n" + line + "\n"
        galaxy_readme.write_text(text, encoding="utf-8")

    print(
        f"Wrote Neutral_Free registries: {len(free)} objects "
        f"(stars={counts['star']}, holes={counts['black_hole']}, "
        f"junctions={counts['junction']})"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
