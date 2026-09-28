"""Build a transparent polity-only texture over the unchanged Galaxy-map base."""

from __future__ import annotations

import io
import math
from pathlib import Path

import boto3
import numpy as np
import requests
from botocore.client import Config
from dotenv import dotenv_values
from PIL import Image, ImageDraw, ImageFont
from scipy.ndimage import (
    binary_closing,
    binary_dilation,
    binary_fill_holes,
    center_of_mass,
    distance_transform_edt,
    label as component_labels,
)


ROOT = Path(__file__).resolve().parents[1]
CANON = ROOT.parent / "EfolsMiradinsPact" / "assets"
TERRITORY_PLATE = CANON / "galaxy_territory_plate.png"
BASE_PLATE = CANON / "galaxy_base_plate.png"
ENV_PATH = ROOT / "server" / "services" / "asset-service" / ".env"
GALAXY_API = "http://galaxyapi.baxic.ru/api/v1/galaxy"
TEXTURE_KEY = "textures/galaxy_territory_plate.png"
SIDE = 2048
MAP_LIMIT = 1.06


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
    territory_mask: np.ndarray,
    center_x: int,
    center_y: int,
) -> tuple[Image.Image, int, int] | None:
    scale = SIDE / 1024
    suzerain = polity.get("kind") == "suzerain"
    maximum = round((15 if suzerain else 9) * scale)
    minimum = max(4, round((4 if suzerain else 3) * scale))
    safe_mask = distance_transform_edt(territory_mask) >= max(2, round(1.5 * scale))

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
            if np.all(safe_mask[top:bottom, left:right][letters]):
                return block, left, top
    return None


def build_overlay(polities: list[dict], systems: list[dict]) -> Image.Image:
    territory = Image.open(TERRITORY_PLATE).convert("RGBA").resize(
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
    delta = rgb - base_rgb
    changed = np.linalg.norm(delta, axis=2) > (2.5 / 255)
    usable = changed & (alpha >= 16) & ~border

    owner = np.full((SIDE, SIDE), -1, dtype=np.int16)
    best_error = np.full((SIDE, SIDE), np.inf, dtype=np.float32)
    best_amount = np.zeros((SIDE, SIDE), dtype=np.float32)
    colors: list[np.ndarray] = []

    for index, polity in enumerate(polities):
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
    system_pixels: dict[str, list[tuple[int, int]]] = {}
    for system in systems:
        stem = system.get("stem")
        if not stem:
            continue
        px = round(
            ((float(system["x"]) + MAP_LIMIT) / (MAP_LIMIT * 2)) * (SIDE - 1)
        )
        py = round(
            (1 - (float(system["y"]) + MAP_LIMIT) / (MAP_LIMIT * 2)) * (SIDE - 1)
        )
        if 0 <= px < SIDE and 0 <= py < SIDE:
            system_pixels.setdefault(stem, []).append((px, py))

    decoded = 0
    for index, polity in enumerate(polities):
        mask = binary_fill_holes(binary_closing(owner == index, iterations=3))
        if int(mask.sum()) < 20:
            print(f"WARNING: no territory decoded for {polity['stem']}")
            continue
        points = system_pixels.get(polity["stem"], [])
        components, count = component_labels(mask)
        component = 0
        target_x = float(np.mean([point[0] for point in points])) if points else SIDE / 2
        target_y = float(np.mean([point[1] for point in points])) if points else SIDE / 2
        if count > 0:
            sizes = np.bincount(components.ravel())
            sizes[0] = 0
            candidates = np.argsort(sizes)[-min(8, count):]
            candidates = candidates[sizes[candidates] >= 200]
            if candidates.size:
                centers = center_of_mass(mask, components, candidates.tolist())
                distances = [
                    (center_x - target_x) ** 2 + (center_y - target_y) ** 2
                    for center_y, center_x in centers
                ]
                component = int(candidates[int(np.argmin(distances))])

        label_mask = components == component if component > 0 else mask
        if points:
            inside_y, inside_x = np.nonzero(label_mask)
            nearest = int(
                np.argmin((inside_x - target_x) ** 2 + (inside_y - target_y) ** 2)
            )
            px, py = int(inside_x[nearest]), int(inside_y[nearest])
        else:
            py_float, px_float = center_of_mass(label_mask)
            py, px = int(round(py_float)), int(round(px_float))

        fitted = fit_label(polity, label_mask, px, py)
        if fitted is None:
            distance = distance_transform_edt(label_mask)
            py, px = np.unravel_index(int(np.argmax(distance)), distance.shape)
            fitted = fit_label(polity, label_mask, int(px), int(py))
        if fitted is None:
            distance = distance_transform_edt(mask)
            py, px = np.unravel_index(int(np.argmax(distance)), distance.shape)
            fitted = fit_label(polity, mask, int(px), int(py))
        if fitted is None:
            print(f"WARNING: label cannot fit inside {polity['stem']}")
            continue
        block, left, top = fitted
        image.alpha_composite(block, (left, top))
        decoded += 1
    print(f"Decoded and labeled {decoded}/{len(polities)} exact painted territories")
    return image


def main() -> int:
    galaxy = requests.get(GALAXY_API, timeout=60).json()
    polities = galaxy.get("polities", [])
    image = build_overlay(polities, galaxy.get("systems", []))
    output = io.BytesIO()
    image.save(output, format="PNG", optimize=True)
    body = output.getvalue()

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
    client.put_object(
        Bucket=bucket,
        Key=TEXTURE_KEY,
        Body=body,
        ContentType="image/png",
        CacheControl="public, max-age=31536000, immutable",
        ACL="public-read",
    )
    print(f"Uploaded transparent overlay ({len(body) / 1024 / 1024:.1f} MB)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
