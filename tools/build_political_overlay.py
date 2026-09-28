"""Build a transparent polity-only texture over the unchanged Galaxy-map base."""

from __future__ import annotations

import io
from pathlib import Path

import boto3
import numpy as np
import requests
from botocore.client import Config
from dotenv import dotenv_values
from PIL import Image, ImageDraw, ImageFont
from scipy.ndimage import binary_dilation, distance_transform_edt


ROOT = Path(__file__).resolve().parents[1]
CANON = ROOT.parent / "EfolsMiradinsPact" / "assets"
TERRITORY_PLATE = CANON / "galaxy_territory_plate.png"
BASE_PLATE = CANON / "galaxy_base_plate.png"
ENV_PATH = ROOT / "server" / "services" / "asset-service" / ".env"
GALAXY_API = "http://galaxyapi.baxic.ru/api/v1/galaxy"
TEXTURE_KEY = "textures/galaxy_territory_plate.png"
SIDE = 1024


def font(size: int, bold: bool = False) -> ImageFont.FreeTypeFont:
    path = Path("C:/Windows/Fonts") / ("seguisb.ttf" if bold else "segoeui.ttf")
    return ImageFont.truetype(str(path), size=size)


def label_lines(polity: dict) -> list[str]:
    text = str(polity.get("label") or polity.get("nameRu") or "").strip()
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    if len(lines) > 1:
        return lines
    words = text.split()
    return [words[0], " ".join(words[1:])] if len(words) > 1 else words


def build_overlay(polities: list[dict]) -> Image.Image:
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
    draw = ImageDraw.Draw(image)
    decoded = 0
    for index, polity in enumerate(polities):
        mask = owner == index
        if int(mask.sum()) < 20:
            print(f"WARNING: no territory decoded for {polity['stem']}")
            continue
        distance = distance_transform_edt(mask)
        py, px = np.unravel_index(int(np.argmax(distance)), distance.shape)
        lines = label_lines(polity)
        if not lines:
            continue
        suzerain = polity.get("kind") == "suzerain"
        size = 15 if suzerain else 9
        text_font = font(size, bold=suzerain)
        line_height = size * 1.12
        for line_index, line in enumerate(lines):
            line_y = py + (line_index - (len(lines) - 1) / 2) * line_height
            draw.text(
                (px, line_y),
                line,
                font=text_font,
                fill=(255, 255, 255, 255),
                stroke_width=3 if suzerain else 2,
                stroke_fill=(0, 0, 0, 220),
                anchor="mm",
                align="center",
            )
        decoded += 1
    print(f"Decoded and labeled {decoded}/{len(polities)} exact painted territories")
    return image


def main() -> int:
    polities = requests.get(GALAXY_API, timeout=60).json().get("polities", [])
    image = build_overlay(polities)
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
