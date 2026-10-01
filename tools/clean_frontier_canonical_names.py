"""Clean display names of the 21 frontier polities without changing tokens."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CATALOG_SERVICE = ROOT / "server" / "services" / "catalog-service"
CANON = ROOT.parent / "EfolsMiradinsPact"
sys.path.insert(0, str(CATALOG_SERVICE))

from app.service.frontier_naming import natural_frontier_star_name  # noqa: E402
from app.service.frontier_polities import (  # noqa: E402
    allocate_frontier_polities,
    map_canonical_frontier_catalog,
)
from app.service.spiral_geometry import generate_arm_objects  # noqa: E402


def main() -> int:
    objects = generate_arm_objects()
    _ownership, clusters = allocate_frontier_polities(objects)
    mapped = map_canonical_frontier_catalog(clusters)
    renames = []
    for object_id, entry in mapped.items():
        if entry["kind"] != "star":
            continue
        _token, name_en, name_ru = natural_frontier_star_name(object_id)
        old_en = entry["nameEn"]
        old_ru = entry["nameRu"]
        if (old_en, old_ru) != (name_en, name_ru):
            renames.append((old_en, old_ru, name_en, name_ru))

    changed_files = 0
    replacements = 0
    for path in CANON.rglob("*.md"):
        text = path.read_text(encoding="utf-8")
        updated = text
        for old_en, old_ru, name_en, name_ru in renames:
            pairs = (
                (f"# {old_en} / {old_ru}", f"# {name_en} / {name_ru}"),
                (f"# {old_ru} / {old_en}", f"# {name_ru} / {name_en}"),
                (f"[`{old_en}`]", f"[`{name_en}`]"),
                (f"[`{old_ru}`]", f"[`{name_ru}`]"),
            )
            for old, new in pairs:
                count = updated.count(old)
                if count:
                    replacements += count
                    updated = updated.replace(old, new)
        if updated != text:
            path.write_text(updated, encoding="utf-8")
            changed_files += 1

    print(
        f"Cleaned {len(renames)} canonical star names in "
        f"{changed_files} files ({replacements} replacements)"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
