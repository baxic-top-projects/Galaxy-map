"""Place polity labels at geometric centroids of their bounded regions."""

from __future__ import annotations

import json
from pathlib import Path

import cv2
import numpy as np


ROOT = Path(__file__).resolve().parents[1]
TERRITORY_MAP = (
    ROOT.parent / "EfolsMiradinsPact" / "assets" / "galaxy_territory_plate.png"
)
SEED_ANCHORS = ROOT / "client" / "src" / "lib" / "galaxy" / "polityLabelAnchors.json"
OUTPUTS = (
    ROOT / "tools" / "polity_label_anchors.json",
    SEED_ANCHORS,
)


def main() -> int:
    territory = cv2.imread(str(TERRITORY_MAP), cv2.IMREAD_UNCHANGED)
    if territory is None or territory.shape[2] != 4:
        raise RuntimeError(f"Cannot read RGBA territory map: {TERRITORY_MAP}")
    image = territory[..., :3].copy()
    alpha = territory[..., 3]
    height, width = alpha.shape
    seeds = json.loads(SEED_ANCHORS.read_text(encoding="utf-8"))
    stems = list(seeds)

    markers = np.zeros((height, width), dtype=np.int32)
    markers[alpha < 8] = 1
    for marker, stem in enumerate(stems, start=2):
        x, y = seeds[stem]
        cv2.circle(
            markers,
            (round(x * (width - 1)), round(y * (height - 1))),
            4,
            marker,
            -1,
        )
    cv2.watershed(image, markers)

    normalized = {}
    for marker, stem in enumerate(stems, start=2):
        ys, xs = np.nonzero((markers == marker) & (alpha > 16))
        if xs.size == 0:
            raise RuntimeError(f"No bounded territory found for {stem}")
        normalized[stem] = [
            round(float(xs.mean() / (width - 1)), 9),
            round(float(ys.mean() / (height - 1)), 9),
        ]
    serialized = json.dumps(normalized, ensure_ascii=False, indent=2) + "\n"
    for output in OUTPUTS:
        output.write_text(serialized, encoding="utf-8")
    print(f"Wrote {len(normalized)} geometric territory centroids")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
