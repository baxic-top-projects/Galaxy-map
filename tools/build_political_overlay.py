"""Build a transparent polity-only texture over the unchanged Galaxy-map base."""

from __future__ import annotations

import ast
import io
import json
import math
from pathlib import Path
import subprocess
import sys

import boto3
import numpy as np
import requests
from botocore.client import Config
from dotenv import dotenv_values
from PIL import Image, ImageDraw, ImageFont
from scipy.ndimage import binary_dilation, label


ROOT = Path(__file__).resolve().parents[1]
CANON = ROOT.parent / "EfolsMiradinsPact" / "assets"
POLITICAL_MAP = CANON / "galaxy_political_map.png"
BASE_PLATE = CANON / "galaxy_base_plate.png"
LOCAL_TERRITORY_OUTPUT = CANON / "galaxy_territory_plate.png"
ENV_PATH = ROOT / "server" / "services" / "asset-service" / ".env"
GALAXY_API = "http://galaxyapi.baxic.ru/api/v1/galaxy"
TEXTURE_KEY = "textures/galaxy_territory_plate.png"
SIDE = 2048
ANCHORS_PATH = ROOT / "tools" / "polity_label_anchors.json"
CANONICAL_RENDERER = ROOT.parent / "EfolsMiradinsPact" / "tools" / "_render_galaxy_political_map.py"


def font(size: int, bold: bool = False) -> ImageFont.FreeTypeFont:
    path = Path("C:/Windows/Fonts") / ("seguisb.ttf" if bold else "segoeui.ttf")
    return ImageFont.truetype(str(path), size=size)


def label_line_candidates(polity: dict) -> list[list[str]]:
    text = str(polity.get("label") or polity.get("nameRu") or "").strip()
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    if len(lines) > 1:
        return [lines]
    words = text.split()
    if len(words) < 2:
        return [words]
    candidates: list[list[str]] = []
    for split in range(1, len(words)):
        candidates.append([" ".join(words[:split]), " ".join(words[split:])])
    if len(words) >= 3:
        for first in range(1, len(words) - 1):
            for second in range(first + 1, len(words)):
                candidates.append(
                    [
                        " ".join(words[:first]),
                        " ".join(words[first:second]),
                        " ".join(words[second:]),
                    ]
                )
    return candidates


def render_label_block(
    lines: list[str],
    size: int,
    bold: bool,
    stroke_width: int,
) -> Image.Image:
    text_font = font(size, bold=bold)
    text = "\n".join(lines)
    spacing = max(1, round(size * 0.12))
    probe = Image.new("L", (1, 1))
    probe_draw = ImageDraw.Draw(probe)
    left, top, right, bottom = probe_draw.multiline_textbbox(
        (0, 0),
        text,
        font=text_font,
        spacing=spacing,
        align="center",
        stroke_width=stroke_width,
        anchor="mm",
    )
    width = max(1, math.ceil(right - left + 2))
    height = max(1, math.ceil(bottom - top + 2))
    block = Image.new("RGBA", (width, height))
    block_draw = ImageDraw.Draw(block)
    block_draw.multiline_text(
        (width / 2, height / 2),
        text,
        font=text_font,
        fill=(255, 255, 255, 255),
        stroke_width=stroke_width,
        stroke_fill=(0, 0, 0, 220),
        spacing=spacing,
        anchor="mm",
        align="center",
    )
    return block


def fit_label(
    polity: dict,
    safe_mask: np.ndarray,
    occupied: np.ndarray,
    center_x: int,
    center_y: int,
) -> tuple[Image.Image, int, int] | None:
    scale = SIDE / 1024
    suzerain = polity.get("kind") == "suzerain"
    maximum = round((15 if suzerain else 9) * scale)
    minimum = max(3, round((3 if suzerain else 2) * scale))

    for size in range(maximum, minimum - 1, -1):
        stroke_width = max(1, round((3 if suzerain else 2) * scale * size / maximum))
        options = []
        for lines in label_line_candidates(polity):
            block = render_label_block(lines, size, suzerain, stroke_width)
            options.append((block.width * block.height, block))
        for _area, block in sorted(options, key=lambda item: item[0]):
            left = round(center_x - block.width / 2)
            top = round(center_y - block.height / 2)
            right = left + block.width
            bottom = top + block.height
            if left < 0 or top < 0 or right > SIDE or bottom > SIDE:
                continue
            letters = np.asarray(block.getchannel("A")) > 0
            if (
                np.all(safe_mask[top:bottom, left:right][letters])
                and not np.any(occupied[top:bottom, left:right][letters])
            ):
                return block, left, top
    return None


def canonical_labels() -> dict[str, str]:
    tree = ast.parse(CANONICAL_RENDERER.read_text(encoding="utf-8"))
    for node in tree.body:
        if (
            isinstance(node, ast.Assign)
            and any(isinstance(target, ast.Name) and target.id == "SHORT_RU" for target in node.targets)
        ):
            return ast.literal_eval(node.value)
    raise RuntimeError("SHORT_RU not found in canonical renderer")


def political_colors() -> dict[str, np.ndarray]:
    tools = CANON.parent / "tools"
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


def build_overlay(polities: list[dict]) -> Image.Image:
    territory = Image.open(POLITICAL_MAP).convert("RGBA").resize(
        (SIDE, SIDE), Image.Resampling.LANCZOS
    )
    base = Image.open(BASE_PLATE).convert("RGB").resize(
        (SIDE, SIDE), Image.Resampling.LANCZOS
    )
    source = np.asarray(territory, dtype=np.uint8)
    rgb = source[..., :3].astype(np.float32) / 255.0
    base_rgb = np.asarray(base, dtype=np.float32) / 255.0 * 0.78
    alpha = source[..., 3]

    cream = np.asarray([247, 240, 214], dtype=np.float32) / 255.0
    border = (np.linalg.norm(rgb - cream, axis=2) < (52 / 255)) & (alpha > 80)
    border = binary_dilation(border, iterations=1)
    # The border network is connected. Discard detached cream labels, title,
    # stars and legend symbols from the rendered political map.
    components, component_count = label(border)
    if component_count:
        sizes = np.bincount(components.ravel())
        sizes[0] = 0
        border = components == int(np.argmax(sizes))
    delta = rgb - base_rgb
    changed = np.linalg.norm(delta, axis=2) > (2.5 / 255)
    usable = changed & (alpha >= 16) & ~border

    owner = np.full((SIDE, SIDE), -1, dtype=np.int16)
    best_error = np.full((SIDE, SIDE), np.inf, dtype=np.float32)
    best_amount = np.zeros((SIDE, SIDE), dtype=np.float32)
    colors: list[np.ndarray] = []
    map_colors = political_colors()

    for index, polity in enumerate(polities):
        color = map_colors.get(polity["stem"])
        if color is None:
            value = str(polity.get("color") or "#000000").lstrip("#")
            color = np.asarray(
                [int(value[offset:offset + 2], 16) for offset in (0, 2, 4)],
                dtype=np.float32,
            ) / 255.0
        colors.append(color)
        direction = color - base_rgb
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
        best_amount[better] = amount[better]

    # Reject text, markers and corridors whose colors do not fit polity paint.
    owner[best_error > 0.0025] = -1
    output = np.zeros((SIDE, SIDE, 4), dtype=np.uint8)
    for index, color in enumerate(colors):
        mask = owner == index
        output[mask, :3] = np.round(color * 255).astype(np.uint8)
        output[mask, 3] = np.round(np.clip(best_amount[mask], 0.0, 0.42) * 255).astype(
            np.uint8
        )
    output[border, :3] = np.asarray([247, 240, 214], dtype=np.uint8)
    output[border, 3] = 255

    image = Image.fromarray(output, "RGBA")
    return image


def main() -> int:
    # Rebuild both canonical outputs from one ownership field. This is the only
    # lossless way to match borders hidden by labels and the legend in the
    # flattened political PNG.
    political_map_bytes = POLITICAL_MAP.read_bytes()
    territory_map_bytes = LOCAL_TERRITORY_OUTPUT.read_bytes()
    try:
        subprocess.run([sys.executable, str(CANONICAL_RENDERER)], check=True)
        generated_territory = LOCAL_TERRITORY_OUTPUT.read_bytes()
    finally:
        # EfolsMiradinsPact is an input only. The renderer writes both files, so
        # restore them after capturing the clean generated territory texture.
        POLITICAL_MAP.write_bytes(political_map_bytes)
        LOCAL_TERRITORY_OUTPUT.write_bytes(territory_map_bytes)
    env = dotenv_values(ENV_PATH)
    bucket = env.get("ASSET_S3_BUCKET") or "galaxybucket"
    endpoint = env.get("ASSET_S3_ENDPOINT_URL") or "https://storage.yandexcloud.net"
    client = boto3.client(
        "s3",
        region_name=env.get("ASSET_S3_REGION") or "ru-central1",
        endpoint_url=endpoint,
        aws_access_key_id=env.get("ASSET_S3_ACCESS_KEY_ID"),
        aws_secret_access_key=env.get("ASSET_S3_SECRET_ACCESS_KEY"),
        config=Config(signature_version="s3v4"),
    )
    image = Image.open(io.BytesIO(generated_territory)).convert("RGBA")
    output = io.BytesIO()
    image.save(output, format="PNG", optimize=True)
    body = output.getvalue()
    client.put_object(
        Bucket=bucket,
        Key=TEXTURE_KEY,
        Body=body,
        ContentType="image/png",
        CacheControl="public, max-age=31536000, immutable",
        ACL="public-read",
    )
    print(
        f"Uploaded political-map territory overlay to s3://{bucket}/{TEXTURE_KEY} "
        f"({len(body) / 1024 / 1024:.1f} MB)"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
