"""Update only the remaining free-object count in EfolsMiradinsPact READMEs."""

from __future__ import annotations

import json
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CANON = ROOT.parent / "EfolsMiradinsPact"
API = "https://galaxyapi.baxic.ru/api/v1/galaxy"


def _free_counts() -> tuple[int, dict[str, int]]:
    request = urllib.request.Request(API, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(request, timeout=120) as response:
        data = json.load(response)
    by_kind = {"star": 0, "black_hole": 0, "junction": 0}
    for system in data.get("systems") or []:
        if (
            str(system.get("id") or "").startswith("frontier:")
            and not system.get("stem")
            and system.get("kind") in by_kind
        ):
            by_kind[str(system["kind"])] += 1
    return sum(by_kind.values()), by_kind


def _patch(path: Path, marker: str, block: str) -> None:
    text = path.read_text(encoding="utf-8")
    if marker in text:
        before, rest = text.split(marker, 1)
        after_parts = rest.split("\n## ", 1)
        after = ("\n## " + after_parts[1]) if len(after_parts) > 1 else ""
        text = before.rstrip() + "\n\n" + block + after
    else:
        text = text.rstrip() + "\n\n" + block
    path.write_text(text, encoding="utf-8")


def main() -> int:
    free, by_kind = _free_counts()
    _patch(
        CANON / "UNIVERSE" / "GALAXY" / "FRONTIER_SYSTEMS" / "EN" / "README.md",
        "## Free neutral objects",
        f"## Free neutral objects\n\n"
        f"Unowned arm objects remaining on the live map: **{free}**  \n"
        f"(stars: **{by_kind['star']}**; black holes: **{by_kind['black_hole']}**; "
        f"junctions: **{by_kind['junction']}**).\n",
    )
    _patch(
        CANON / "UNIVERSE" / "GALAXY" / "FRONTIER_SYSTEMS" / "RU" / "README.md",
        "## Свободные нейтральные объекты",
        f"## Свободные нейтральные объекты\n\n"
        f"Свободных объектов рукавов на текущей карте: **{free}**  \n"
        f"(звёзд: **{by_kind['star']}**; чёрных дыр: **{by_kind['black_hole']}**; "
        f"стыков: **{by_kind['junction']}**).\n",
    )

    galaxy_readme = CANON / "UNIVERSE" / "GALAXY" / "README.md"
    lines = []
    for line in galaxy_readme.read_text(encoding="utf-8").splitlines():
        if "`FRONTIER_SYSTEMS/`" in line:
            lines.append(
                "- `FRONTIER_SYSTEMS/` — дополнительные системы держав на спиральных рукавах; "
                f"свободных нейтральных объектов: **{free}** "
                f"(звёзд: **{by_kind['star']}**)"
            )
        else:
            lines.append(line)
    if not any("`FRONTIER_SYSTEMS/`" in line for line in lines):
        # insert before RESOURCES line if present
        out = []
        inserted = False
        for line in lines:
            if not inserted and "`RESOURCES_" in line:
                out.append(
                    "- `FRONTIER_SYSTEMS/` — дополнительные системы держав на спиральных рукавах; "
                    f"свободных нейтральных объектов: **{free}** "
                    f"(звёзд: **{by_kind['star']}**)"
                )
                inserted = True
            out.append(line)
        lines = out
    galaxy_readme.write_text("\n".join(lines) + "\n", encoding="utf-8")

    # Remove accidental full registries if present.
    for path in (
        CANON / "UNIVERSE" / "GALAXY" / "FRONTIER_SYSTEMS" / "EN" / "Neutral_Free.md",
        CANON
        / "UNIVERSE"
        / "GALAXY"
        / "FRONTIER_SYSTEMS"
        / "RU"
        / "Свободные_нейтральные.md",
    ):
        if path.is_file():
            path.unlink()

    print(
        f"Updated free-object count: {free} "
        f"(stars={by_kind['star']}, black_holes={by_kind['black_hole']}, "
        f"junctions={by_kind['junction']})"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
