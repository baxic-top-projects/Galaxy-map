"""Prepare the generated photorealistic four-arm galaxy texture."""

from __future__ import annotations

from pathlib import Path

import numpy as np
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
OUTER_ARMS_SOURCE = ROOT / "tools" / "assets" / "galaxy_outer_arms_source.jpg"
CENTRAL_DISK_SOURCE = ROOT / "tools" / "assets" / "galaxy_central_disk_source.png"
OUTPUT = ROOT / "client" / "public" / "textures" / "galaxy_base_plate_v5.png"
SIDE = 2048
MAP_LIMIT = 1.80
CENTRAL_DISK_RADIUS = 1.02


def compose_central_disk(outer: Image.Image) -> Image.Image:
    """Fill the generated center with the supplied dense round galaxy disk."""
    central = Image.open(CENTRAL_DISK_SOURCE).convert("RGB")
    target_width = round(SIDE * 0.80)
    target_height = round(target_width * central.height / central.width)
    central = central.resize((target_width, target_height), Image.Resampling.LANCZOS)
    central_layer = Image.new("RGB", (SIDE, SIDE))
    central_layer.paste(
        central,
        ((SIDE - target_width) // 2, (SIDE - target_height) // 2),
    )
    yy, xx = np.ogrid[:SIDE, :SIDE]
    radius = np.hypot(xx - SIDE / 2, yy - SIDE / 2)
    disk_pixels = CENTRAL_DISK_RADIUS / MAP_LIMIT * SIDE / 2
    feather = SIDE * 0.055
    mask = np.clip((disk_pixels + feather - radius) / feather, 0, 1)[..., None]
    outer_pixels = np.asarray(outer, dtype=np.float32)
    central_pixels = np.asarray(central_layer, dtype=np.float32)
    result = outer_pixels * (1 - mask) + central_pixels * mask
    return Image.fromarray(np.clip(result, 0, 255).astype(np.uint8), mode="RGB")


def main() -> None:
    if not OUTER_ARMS_SOURCE.is_file() or not CENTRAL_DISK_SOURCE.is_file():
        raise FileNotFoundError("Galaxy source images are missing")
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    image = Image.open(OUTER_ARMS_SOURCE).convert("RGB").resize(
        (SIDE, SIDE),
        Image.Resampling.LANCZOS,
    )
    image = compose_central_disk(image)
    image.save(OUTPUT, optimize=True)
    print(f"Wrote {OUTPUT} ({OUTPUT.stat().st_size / 1024 / 1024:.1f} MiB)")


if __name__ == "__main__":
    main()
