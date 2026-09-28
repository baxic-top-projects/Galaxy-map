"""Publish the canonical political map without its bottom legend."""

from __future__ import annotations

import io
from pathlib import Path

import boto3
import numpy as np
import requests
from botocore.client import Config
from PIL import Image, ImageDraw, ImageFont
from scipy.ndimage import (
    binary_dilation,
    distance_transform_edt,
)

try:
    from dotenv import dotenv_values
except ImportError:  # pragma: no cover
    def dotenv_values(path):
        values = {}
        for line in Path(path).read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                key, value = line.split("=", 1)
                values[key.strip()] = value.strip()
        return values


ROOT = Path(__file__).resolve().parents[1]
ENV_PATH = ROOT / "server" / "services" / "asset-service" / ".env"
GALAXY_API = "http://galaxyapi.baxic.ru/api/v1/galaxy"
TEXTURE_KEY = "textures/galaxy_territory_plate.png"
MAP_LIMIT = 1.06
LOCAL_BASE_PLATE = ROOT.parent / "EfolsMiradinsPact" / "assets" / "galaxy_territory_plate.png"
LOCAL_GALAXY_PLATE = ROOT.parent / "EfolsMiradinsPact" / "assets" / "galaxy_base_plate.png"
CANONICAL_POLITICAL_MAP = ROOT.parent / "EfolsMiradinsPact" / "assets" / "galaxy_political_map.png"


def _font(size: int, *, bold: bool = False) -> ImageFont.FreeTypeFont:
    windows = Path("C:/Windows/Fonts")
    candidates = [
        windows / ("seguisb.ttf" if bold else "segoeui.ttf"),
        windows / ("arialbd.ttf" if bold else "arial.ttf"),
        Path("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf" if bold else
             "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"),
    ]
    for path in candidates:
        if path.is_file():
            return ImageFont.truetype(str(path), size=size)
    return ImageFont.load_default()


def _anchors(payload: dict, image: Image.Image) -> list[tuple[dict, float, float]]:
    """Decode each polity's actual painted pixels and find its widest interior."""
    polities = payload.get("polities", [])
    width, height = image.size
    pixels = np.asarray(image, dtype=np.uint8)
    rgb = pixels[..., :3].astype(np.float32) / 255.0
    alpha = pixels[..., 3]
    cream = np.asarray([247, 240, 214], dtype=np.float32) / 255.0
    border = (np.linalg.norm(rgb - cream, axis=2) < (48 / 255)) & (alpha > 100)
    border = binary_dilation(border, iterations=1)
    base = Image.open(LOCAL_GALAXY_PLATE).convert("RGB").resize(
        (width, height),
        Image.Resampling.LANCZOS,
    )
    # The canon renderer dims the galaxy to 78% before applying polity paint.
    base_rgb = np.asarray(base, dtype=np.float32) / 255.0 * 0.78
    painted = np.linalg.norm(rgb - base_rgb, axis=2) > (2.5 / 255)
    usable = painted & (alpha >= 16) & ~border

    own = np.full((height, width), -1, dtype=np.int16)
    best_error = np.full((height, width), np.inf, dtype=np.float32)
    delta = rgb - base_rgb
    for index, polity in enumerate(polities):
        value = str(polity.get("color") or "#000000").lstrip("#")
        color = np.asarray(
            [int(value[offset:offset + 2], 16) for offset in (0, 2, 4)],
            dtype=np.float32,
        ) / 255.0
        direction = color - base_rgb
        amount = np.clip(
            np.sum(delta * direction, axis=2)
            / np.maximum(np.sum(direction * direction, axis=2), 1e-8),
            0.0,
            0.7,
        )
        error = np.sum((delta - amount[..., None] * direction) ** 2, axis=2)
        better = usable & (amount > 0.04) & (error < best_error)
        own[better] = index
        best_error[better] = error[better]

    anchors = []
    for index, polity in enumerate(polities):
        mask = own == index
        if int(mask.sum()) < 20:
            print(f"WARNING: no painted territory decoded for {polity['stem']}")
            continue
        interior = distance_transform_edt(mask)
        py, px = np.unravel_index(int(np.argmax(interior)), interior.shape)
        x = (px / max(width - 1, 1)) * MAP_LIMIT * 2 - MAP_LIMIT
        y = MAP_LIMIT - (py / max(height - 1, 1)) * MAP_LIMIT * 2
        anchors.append((polity, float(x), float(y)))
    print(f"Decoded {len(anchors)}/{len(polities)} labels from exact territory colors")
    return anchors


def _label_lines(polity: dict) -> list[str]:
    text = str(polity.get("label") or polity.get("nameRu") or "").strip()
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    if len(lines) > 1:
        return lines
    words = text.split()
    return [words[0], " ".join(words[1:])] if len(words) > 1 else words


def main() -> int:
    env = dotenv_values(ENV_PATH)
    bucket = env.get("ASSET_S3_BUCKET") or "galaxybucket"
    endpoint = env.get("ASSET_S3_ENDPOINT_URL") or "https://storage.yandexcloud.net"
    public_base = (
        env.get("ASSET_S3_PUBLIC_BASE_URL")
        or f"{endpoint.rstrip('/')}/{bucket}"
    ).rstrip("/")

    if not CANONICAL_POLITICAL_MAP.is_file():
        raise SystemExit(
            f"Missing canonical political map: {CANONICAL_POLITICAL_MAP}"
        )
    image = Image.open(CANONICAL_POLITICAL_MAP).convert("RGBA")
    clean_plate = Image.open(LOCAL_BASE_PLATE).convert("RGBA").resize(
        image.size,
        Image.Resampling.LANCZOS,
    )
    # Both legend panels occupy the bottom 19.5% of the canonical render.
    # Restore that band from the matching clean plate; the interactive scene
    # continues to draw its hypercorridors and stars above this texture.
    legend_top = round(image.height * 0.805)
    image.paste(
        clean_plate.crop((0, legend_top, image.width, image.height)),
        (0, legend_top),
    )
    output = io.BytesIO()
    image.save(output, format="PNG", optimize=True)
    output.seek(0)

    client = boto3.client(
        "s3",
        region_name=env.get("ASSET_S3_REGION") or "ru-central1",
        endpoint_url=endpoint,
        aws_access_key_id=env.get("ASSET_S3_ACCESS_KEY_ID"),
        aws_secret_access_key=env.get("ASSET_S3_SECRET_ACCESS_KEY"),
        config=Config(signature_version="s3v4"),
    )
    client.put_object(
        Bucket=bucket,
        Key=TEXTURE_KEY,
        Body=output.getvalue(),
        ContentType="image/png",
        CacheControl="public, max-age=31536000, immutable",
        ACL="public-read",
    )
    print(f"Uploaded s3://{bucket}/{TEXTURE_KEY} ({len(output.getvalue()) / 1024 / 1024:.1f} MB)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

