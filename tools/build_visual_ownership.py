"""Map every API system to the exact canonical clean territory plate."""

from __future__ import annotations

import json
from pathlib import Path
import sys

import numpy as np
import requests
from PIL import Image
from scipy.ndimage import binary_dilation, label


ROOT = Path(__file__).resolve().parents[1]
CANON_ASSETS = ROOT.parent / "EfolsMiradinsPact" / "assets"
OUTPUT = ROOT / "client" / "src" / "lib" / "galaxy" / "visualOwnership.json"
LABEL_ANCHORS = ROOT / "client" / "src" / "lib" / "galaxy" / "polityLabelAnchors.json"
TERRITORY_MAP = CANON_ASSETS / "galaxy_territory_plate.png"
GALAXY_API = "http://galaxyapi.baxic.ru/api/v1/galaxy"
MAP_LIMIT = 1.06


def political_colors() -> dict[str, np.ndarray]:
    tools = CANON_ASSETS.parent / "tools"
    sys.path.insert(0, str(tools))
    from _render_galaxy_political_map import POLITY_ROWS, polity_color

    colors = {}
    raih_index = 0
    miradin_index = 0
    for stem, _ru, _en, _name_ru, bloc, kind, _arch in POLITY_ROWS:
        index = raih_index if bloc == "raih" else miradin_index
        colors[stem] = np.asarray(
            polity_color(stem, bloc, kind, index),
            dtype=np.float32,
        )
        if bloc == "raih":
            raih_index += 1
        elif bloc == "miradin":
            miradin_index += 1
    return colors


def decode_owner(polities: list[dict]) -> np.ndarray:
    territory_image = Image.open(TERRITORY_MAP).convert("RGBA")
    width, height = territory_image.size
    territory = np.asarray(territory_image, dtype=np.uint8)
    base = np.asarray(
        Image.open(CANON_ASSETS / "galaxy_base_plate.png")
        .convert("RGB")
        .resize((width, height), Image.Resampling.LANCZOS),
        dtype=np.float32,
    ) / 255.0 * 0.78
    rgb = territory[..., :3].astype(np.float32) / 255.0
    alpha = territory[..., 3]
    cream = np.asarray([247, 240, 214], dtype=np.float32) / 255.0
    border = binary_dilation(
        (np.linalg.norm(rgb - cream, axis=2) < (52 / 255)) & (alpha > 80),
        iterations=1,
    )
    delta = rgb - base
    usable = (
        (np.linalg.norm(delta, axis=2) > (2.5 / 255))
        & (alpha >= 16)
        & ~border
    )
    owner = np.full((height, width), -1, dtype=np.int16)
    best_error = np.full((height, width), np.inf, dtype=np.float32)
    map_colors = political_colors()

    for index, polity in enumerate(polities):
        color = map_colors.get(polity["stem"])
        if color is None:
            value = polity["color"].lstrip("#")
            color = np.asarray(
                [int(value[offset:offset + 2], 16) for offset in (0, 2, 4)],
                dtype=np.float32,
            ) / 255.0
        direction = color - base
        amount = np.clip(
            np.sum(delta * direction, axis=2)
            / np.maximum(np.sum(direction * direction, axis=2), 1e-8),
            0.0,
            0.7,
        )
        error = np.sum((delta - amount[..., None] * direction) ** 2, axis=2)
        better = usable & (amount > 0.035) & (error < best_error)
        owner[better] = index
        best_error[better] = error[better]

    # Similar brown/purple fills can classify individual stars as a
    # neighboring polity. Closed cream borders are authoritative: if a
    # connected region contains exactly one polity label anchor, assign the
    # entire region to that polity. Regions sharing multiple anchors retain
    # the color result above (the galactic core interrupts one such border).
    anchors = json.loads(LABEL_ANCHORS.read_text(encoding="utf-8"))
    strong_border = binary_dilation(
        (np.linalg.norm(rgb - cream, axis=2) < (125 / 255)) & (alpha > 40),
        iterations=12,
    )
    regions, _region_count = label((alpha > 16) & ~strong_border)
    indices_by_region: dict[int, list[int]] = {}
    for index, polity in enumerate(polities):
        anchor = anchors.get(polity["stem"])
        if not anchor:
            continue
        px = round(float(anchor[0]) * (width - 1))
        py = round(float(anchor[1]) * (height - 1))
        region = int(regions[py, px])
        if region > 0:
            indices_by_region.setdefault(region, []).append(index)
    for region, indices in indices_by_region.items():
        if len(indices) == 1:
            owner[regions == region] = indices[0]
    return owner


def visual_owner(owner: np.ndarray, x: float, y: float) -> int | None:
    height, width = owner.shape
    px = round(((x + MAP_LIMIT) / (MAP_LIMIT * 2)) * (width - 1))
    py = round((1 - (y + MAP_LIMIT) / (MAP_LIMIT * 2)) * (height - 1))
    for radius in (4, 8, 16, 32):
        values = owner[
            max(0, py - radius):min(height, py + radius + 1),
            max(0, px - radius):min(width, px + radius + 1),
        ].ravel()
        values = values[values >= 0]
        if values.size:
            ids, hits = np.unique(values, return_counts=True)
            return int(ids[int(np.argmax(hits))])
    return None


def main() -> int:
    galaxy = requests.get(GALAXY_API, timeout=60).json()
    polities = galaxy.get("polities", [])
    owner = decode_owner(polities)
    anchors = json.loads(LABEL_ANCHORS.read_text(encoding="utf-8"))
    overrides = {}
    unresolved = []
    for system in galaxy.get("systems", []):
        if (
            system.get("kind") == "well"
            or system.get("token") == "AxisWell"
            or system.get("id") == "AxisWell"
        ):
            continue
        index = visual_owner(owner, float(system["x"]), float(system["y"]))
        if index is None:
            unresolved.append(system["id"])
            continue
        stem = polities[index]["stem"]
        if stem == "Aquarian_Republic":
            normalized_x = (float(system["x"]) + MAP_LIMIT) / (MAP_LIMIT * 2)
            normalized_y = (MAP_LIMIT - float(system["y"])) / (MAP_LIMIT * 2)
            nearest = min(
                anchors,
                key=lambda candidate: (
                    (normalized_x - anchors[candidate][0]) ** 2
                    + (normalized_y - anchors[candidate][1]) ** 2
                ),
            )
            if nearest == "Astrean_Consortium":
                stem = "Astrean_Consortium"
        if stem != system.get("stem"):
            overrides[system["id"]] = stem

    OUTPUT.write_text(
        json.dumps(overrides, ensure_ascii=False, separators=(",", ":"), sort_keys=True),
        encoding="utf-8",
    )
    print(
        f"Wrote {OUTPUT}: {len(overrides)} ownership corrections, "
        f"{len(unresolved)} unresolved systems"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
