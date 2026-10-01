"""Write map-assigned frontier ownership registries to EfolsMiradinsPact."""

from __future__ import annotations

import sys
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CATALOG_SERVICE = ROOT / "server" / "services" / "catalog-service"
CANON = ROOT.parent / "EfolsMiradinsPact"

sys.path.insert(0, str(CATALOG_SERVICE))
sys.path.insert(0, str(CANON / "tools"))

from _gen_states_planets import EN_TO_RU  # noqa: E402
from app.service.frontier_polities import (  # noqa: E402
    FRONTIER_POLITIES,
    allocate_frontier_polities,
    assign_objects_inside_territories,
)
from app.service.spiral_arm_service import _generated_claim_catalog  # noqa: E402
from app.service.spiral_geometry import generate_arm_objects  # noqa: E402


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


def _document(stem: str, ru_stem: str, entries: list[dict], *, ru: bool) -> str:
    counts = Counter(entry["kind"] for entry in entries)
    if ru:
        title = f"# {ru_stem} — дополнительные системы на карте"
        intro = (
            "Реестр объектов спиральных рукавов, которые находились внутри или "
            "касались уже зафиксированной границы державы и получили её принадлежность. "
            "Это дополнение к исходным каноническим карточкам систем; координаты "
            "объектов не изменялись."
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
        title = f"# {stem} — additional map systems"
        intro = (
            "Registry of spiral-arm objects that were already inside or "
            "touching this polity's fixed rendered boundary and therefore received its "
            "ownership. This supplements the original canonical system cards; "
            "object coordinates were not changed."
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
    return (
        f"{title}\n\n{intro}\n\n{summary}\n\n"
        f"{header}\n{separator}\n" + "\n".join(rows) + "\n"
    )


def _index(rows: list[tuple[str, str, Counter]], *, ru: bool) -> str:
    if ru:
        lines = [
            "# Дополнительные системы новых государств",
            "",
            "Канонический реестр объектов, назначенных по попаданию внутрь или "
            "касанию границ 21 нового государства без изменения координат.",
            "",
            "| Государство | Всего | Звёзды | Чёрные дыры | Стыки |",
            "|-------------|-------|--------|-------------|-------|",
        ]
        lines.extend(
            f"| [{ru_stem}]({ru_stem}.md) | {sum(counts.values())} | "
            f"{counts['star']} | {counts['black_hole']} | {counts['junction']} |"
            for _stem, ru_stem, counts in rows
        )
    else:
        lines = [
            "# Additional systems of the new polities",
            "",
            "Canonical registry of objects assigned because they lie inside "
            "or touch the fixed borders of the 21 new polities, without moving them.",
            "",
            "| Polity | Total | Stars | Black holes | Junctions |",
            "|--------|-------|-------|-------------|-----------|",
        ]
        lines.extend(
            f"| [{stem}]({stem}.md) | {sum(counts.values())} | "
            f"{counts['star']} | {counts['black_hole']} | {counts['junction']} |"
            for stem, _ru_stem, counts in rows
        )
    totals = Counter()
    for _stem, _ru_stem, counts in rows:
        totals.update(counts)
    lines.extend(
        [
            "",
            (
                f"**Total: {sum(totals.values())}; stars: {totals['star']}; "
                f"black holes: {totals['black_hole']}; "
                f"junctions: {totals['junction']}.**"
            ),
            "",
        ]
    )
    return "\n".join(lines)


def main() -> int:
    objects = generate_arm_objects()
    ownership, _clusters = allocate_frontier_polities(objects)
    additions = assign_objects_inside_territories(objects, ownership, [])
    by_id = {obj.id: obj for obj in objects}
    grouped: dict[str, list[dict]] = defaultdict(list)

    for object_id, stem in additions.items():
        obj = by_id[object_id]
        named = _generated_claim_catalog(obj, stem)
        grouped[stem].append(
            {
                **named,
                "id": object_id,
                "arm": obj.arm,
                "x": obj.x,
                "y": obj.y,
            }
        )

    en_dir = CANON / "UNIVERSE" / "GALAXY" / "FRONTIER_SYSTEMS" / "EN"
    ru_dir = CANON / "UNIVERSE" / "GALAXY" / "FRONTIER_SYSTEMS" / "RU"
    en_dir.mkdir(parents=True, exist_ok=True)
    ru_dir.mkdir(parents=True, exist_ok=True)
    index_rows = []

    for polity in FRONTIER_POLITIES:
        entries = sorted(
            grouped[polity.stem],
            key=lambda entry: (entry["kind"], entry["token"]),
        )
        ru_stem = EN_TO_RU[polity.stem]
        (en_dir / f"{polity.stem}.md").write_text(
            _document(polity.stem, ru_stem, entries, ru=False),
            encoding="utf-8",
        )
        (ru_dir / f"{ru_stem}.md").write_text(
            _document(polity.stem, ru_stem, entries, ru=True),
            encoding="utf-8",
        )
        index_rows.append(
            (
                polity.stem,
                ru_stem,
                Counter(entry["kind"] for entry in entries),
            )
        )

    (en_dir / "README.md").write_text(
        _index(index_rows, ru=False),
        encoding="utf-8",
    )
    (ru_dir / "README.md").write_text(
        _index(index_rows, ru=True),
        encoding="utf-8",
    )
    print(
        f"Wrote {len(index_rows) * 2 + 2} documents with "
        f"{len(additions)} frontier objects"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
