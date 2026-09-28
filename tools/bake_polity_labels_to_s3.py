"""Bake polity labels into the S3 territory plate and upload it in place."""

from __future__ import annotations

import io
from pathlib import Path

import boto3
import requests
from botocore.client import Config
from PIL import Image, ImageDraw, ImageFont

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


def _anchors(payload: dict) -> list[tuple[dict, float, float]]:
    systems_by_stem: dict[str, list[dict]] = {}
    for system in payload.get("systems", []):
        stem = system.get("stem")
        if stem:
            systems_by_stem.setdefault(stem, []).append(system)

    anchors = []
    for polity in payload.get("polities", []):
        systems = systems_by_stem.get(polity.get("stem"), [])
        if not systems:
            continue
        mean_x = sum(float(system["x"]) for system in systems) / len(systems)
        mean_y = sum(float(system["y"]) for system in systems) / len(systems)
        anchor = min(
            systems,
            key=lambda system: (float(system["x"]) - mean_x) ** 2
            + (float(system["y"]) - mean_y) ** 2,
        )
        anchors.append((polity, float(anchor["x"]), float(anchor["y"])))
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

    galaxy = requests.get(GALAXY_API, timeout=60).json()
    source_url = f"{public_base}/{TEXTURE_KEY}?source=labels-v1"
    response = requests.get(source_url, timeout=120)
    response.raise_for_status()
    image = Image.open(io.BytesIO(response.content)).convert("RGBA")
    draw = ImageDraw.Draw(image)
    width, height = image.size
    scale = width / 1024

    for polity, x, y in _anchors(galaxy):
        lines = _label_lines(polity)
        if not lines:
            continue
        suzerain = polity.get("kind") == "suzerain"
        font_size = max(7, round((15 if suzerain else 8.5) * scale))
        font = _font(font_size, bold=suzerain)
        line_height = font_size * 1.12
        px = ((x + MAP_LIMIT) / (MAP_LIMIT * 2)) * width
        py = (1 - (y + MAP_LIMIT) / (MAP_LIMIT * 2)) * height
        for index, line in enumerate(lines):
            line_y = py + (index - (len(lines) - 1) / 2) * line_height
            draw.text(
                (px, line_y),
                line,
                font=font,
                fill=(255, 255, 255, 255),
                stroke_width=max(2, round((3.2 if suzerain else 2.4) * scale)),
                stroke_fill=(0, 0, 0, 210),
                anchor="mm",
                align="center",
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

