"""Recalculate polity label anchors from EfolsMiradinsPact territory pixels."""

from __future__ import annotations

import json
from pathlib import Path

from PIL import Image

from bake_polity_labels_to_s3 import LOCAL_BASE_PLATE, MAP_LIMIT, _anchors
from export_galaxy import _rgb_hex, build_rows


ROOT = Path(__file__).resolve().parents[1]
OUTPUTS = (
    ROOT / "tools" / "polity_label_anchors.json",
    ROOT / "client" / "src" / "lib" / "galaxy" / "polityLabelAnchors.json",
)


def main() -> int:
    polities = [
        {
            "stem": row["stem"],
            "nameEn": row["name_en"],
            "nameRu": row["name_ru"],
            "kind": row["kind"],
            "color": _rgb_hex(row["color"]),
        }
        for row in build_rows()
    ]
    image = Image.open(LOCAL_BASE_PLATE).convert("RGBA")
    normalized = {
        polity["stem"]: [
            round((x + MAP_LIMIT) / (MAP_LIMIT * 2), 9),
            round((MAP_LIMIT - y) / (MAP_LIMIT * 2), 9),
        ]
        for polity, x, y in _anchors({"polities": polities}, image)
    }
    if len(normalized) != len(polities):
        raise RuntimeError(
            f"Decoded only {len(normalized)}/{len(polities)} polity territories"
        )
    serialized = json.dumps(normalized, ensure_ascii=False, indent=2) + "\n"
    for output in OUTPUTS:
        output.write_text(serialized, encoding="utf-8")
    print(f"Wrote {len(normalized)} polity anchors")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
