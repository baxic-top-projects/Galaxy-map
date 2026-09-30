"""Place polity labels at interior centers of their largest territory regions."""

from __future__ import annotations

import json
from pathlib import Path

import cv2
import numpy as np
from scipy import ndimage


ROOT = Path(__file__).resolve().parents[1]
TERRITORY_MAP = (
    ROOT.parent / "EfolsMiradinsPact" / "assets" / "galaxy_territory_plate.png"
)
SEED_ANCHORS = ROOT / "client" / "src" / "lib" / "galaxy" / "polityLabelAnchors.json"
OUTPUTS = (
    ROOT / "tools" / "polity_label_anchors.json",
    SEED_ANCHORS,
)


def interior_anchor(mask: np.ndarray) -> tuple[float, float]:
    """Return (x, y) pixel of the largest component's pole of inaccessibility."""
    labeled, count = ndimage.label(mask, structure=np.array([[0, 1, 0], [1, 1, 1], [0, 1, 0]]))
    if count <= 0:
        raise RuntimeError("empty territory mask")
    sizes = ndimage.sum(mask, labeled, index=np.arange(1, count + 1))
    best = int(np.argmax(sizes)) + 1
    component = labeled == best
    # Distance to exterior (False pixels); border pixels get low values.
    distance = ndimage.distance_transform_edt(component)
    # Prefer deepest interior; break ties toward component centroid.
    ys, xs = np.nonzero(component)
    cy = float(ys.mean())
    cx = float(xs.mean())
    flat = distance.reshape(-1)
    candidates = np.flatnonzero(component.reshape(-1))
    best_score = -1.0
    best_tie = float("inf")
    best_y = int(cy)
    best_x = int(cx)
    width = mask.shape[1]
    for index in candidates:
        score = float(flat[index])
        y, x = divmod(index, width)
        tie = (x - cx) ** 2 + (y - cy) ** 2
        if score > best_score or (score == best_score and tie < best_tie):
            best_score = score
            best_tie = tie
            best_x = x
            best_y = y
    return float(best_x), float(best_y)


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
        mask = (markers == marker) & (alpha > 16)
        if not np.any(mask):
            raise RuntimeError(f"No bounded territory found for {stem}")
        x, y = interior_anchor(mask)
        normalized[stem] = [
            round(float(x / (width - 1)), 9),
            round(float(y / (height - 1)), 9),
        ]
    serialized = json.dumps(normalized, ensure_ascii=False, indent=2) + "\n"
    for output in OUTPUTS:
        output.write_text(serialized, encoding="utf-8")
    print(f"Wrote {len(normalized)} interior territory anchors")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
