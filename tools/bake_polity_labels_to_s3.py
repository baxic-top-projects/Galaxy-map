"""Bake polity labels into the S3 territory plate and upload it in place."""

from __future__ import annotations

import io
from collections import Counter, defaultdict
from pathlib import Path

import boto3
import numpy as np
import requests
from botocore.client import Config
from PIL import Image, ImageDraw, ImageFont
from scipy.ndimage import (
    binary_closing,
    binary_dilation,
    distance_transform_edt,
    generate_binary_structure,
    label as component_labels,
)
from scipy.spatial import cKDTree

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
    """Find the fattest interior point of each nearest-system territory."""
    polities = payload.get("polities", [])
    polity_index = {polity["stem"]: index for index, polity in enumerate(polities)}
    systems = [
        system
        for system in payload.get("systems", [])
        if system.get("stem") in polity_index
    ]
    width, height = image.size
    pixels = np.asarray(image, dtype=np.uint8)
    rgb = pixels[..., :3].astype(np.int16)
    alpha = pixels[..., 3]
    cream = np.asarray([247, 240, 214], dtype=np.int16)
    border = (np.linalg.norm(rgb - cream, axis=2) < 48) & (alpha > 100)
    # Remove anti-aliased edge pixels too, otherwise neighboring cells can leak together.
    border = binary_dilation(border, iterations=1)
    interior = (alpha >= 16) & ~border
    components, component_count = component_labels(
        interior,
        structure=generate_binary_structure(2, 1),
    )
    component_votes: dict[int, Counter[str]] = defaultdict(Counter)
    for system in systems:
        px = int(round(((float(system["x"]) + MAP_LIMIT) / (MAP_LIMIT * 2)) * (width - 1)))
        py = int(round((1 - (float(system["y"]) + MAP_LIMIT) / (MAP_LIMIT * 2)) * (height - 1)))
        px = min(width - 1, max(0, px))
        py = min(height - 1, max(0, py))
        component = int(components[py, px])
        if component > 0:
            component_votes[component][system["stem"]] += 1

    components_by_stem: dict[str, list[int]] = defaultdict(list)
    for component, votes in component_votes.items():
        if votes:
            components_by_stem[votes.most_common(1)[0][0]].append(component)

    visual_anchors = []
    for polity in polities:
        candidates = components_by_stem.get(polity["stem"], [])
        if not candidates:
            continue
        component = max(candidates, key=lambda item: int(np.sum(components == item)))
        mask = components == component
        interior_distance = distance_transform_edt(mask)
        py, px = np.unravel_index(int(np.argmax(interior_distance)), interior_distance.shape)
        x = (px / max(width - 1, 1)) * MAP_LIMIT * 2 - MAP_LIMIT
        y = MAP_LIMIT - (py / max(height - 1, 1)) * MAP_LIMIT * 2
        visual_anchors.append((polity, float(x), float(y)))

    print(
        f"Matched {len(visual_anchors)}/{len(polities)} labels directly to PNG territories; "
        "missing labels will use the territory reconstruction"
    )

    points = np.asarray(
        [[float(system["x"]), float(system["y"])] for system in systems],
        dtype=np.float64,
    )
    owners = np.asarray(
        [polity_index[system["stem"]] for system in systems],
        dtype=np.int32,
    )
    tree = cKDTree(points)

    xs = np.linspace(-MAP_LIMIT, MAP_LIMIT, width, dtype=np.float64)
    ys = np.linspace(MAP_LIMIT, -MAP_LIMIT, height, dtype=np.float64)
    own = np.full((height, width), -1, dtype=np.int32)
    nearest_distance = np.full((height, width), np.inf, dtype=np.float64)
    alpha = np.asarray(image.getchannel("A"), dtype=np.uint8)

    # Query in strips to avoid allocating a full multi-million-row coordinate array.
    strip = 96
    for y0 in range(0, height, strip):
        y1 = min(height, y0 + strip)
        xx, yy = np.meshgrid(xs, ys[y0:y1])
        query = np.column_stack([xx.ravel(), yy.ravel()])
        distance, nearest = tree.query(query, k=1, workers=-1)
        own[y0:y1] = owners[np.asarray(nearest, dtype=np.int64)].reshape(y1 - y0, width)
        nearest_distance[y0:y1] = np.asarray(distance).reshape(y1 - y0, width)

    nearest_neighbors = tree.query(points, k=2, workers=-1)[0][:, 1]
    reach = float(np.median(nearest_neighbors)) * 2.35
    xx, yy = np.meshgrid(xs, ys)
    radius = np.hypot(xx, yy)
    star_radius = float(np.max(np.hypot(points[:, 0], points[:, 1])))
    content_radius = min(MAP_LIMIT * 0.995, star_radius + reach * 1.35)
    angle = np.arctan2(yy, xx)
    scallop = (
        0.82
        + 0.22 * (0.5 + 0.5 * np.sin(6.0 * angle) * np.cos(4.0 * angle))
        + 0.10 * (0.5 + 0.5 * np.sin(11.0 * angle + 1.3))
    )
    reach_map = np.full((height, width), reach, dtype=np.float64)
    rim = radius > 0.72
    reach_map[rim] *= scallop[rim]
    paintable = (radius <= content_radius) & (nearest_distance <= reach_map) & (alpha >= 16)
    own[~paintable] = -1

    for index in sorted(range(len(polities)), key=lambda item: int(np.sum(owners == item))):
        mask = own == index
        if int(mask.sum()) >= 80:
            own[binary_closing(mask, iterations=2)] = index

    four = generate_binary_structure(2, 1)
    for _ in range(2):
        for index in range(len(polities)):
            mask = (own == index) & paintable
            components, count = component_labels(mask, structure=four)
            if count <= 1:
                continue
            sizes = np.bincount(components.ravel())
            sizes[0] = 0
            main = int(np.argmax(sizes))
            for component in range(1, count + 1):
                if component == main:
                    continue
                island = components == component
                ring = binary_dilation(island, structure=four) & ~island & paintable
                neighbors = own[ring]
                neighbors = neighbors[(neighbors >= 0) & (neighbors != index)]
                if neighbors.size:
                    values, hits = np.unique(neighbors, return_counts=True)
                    own[island] = int(values[int(np.argmax(hits))])

    visual_stems = {polity["stem"] for polity, _x, _y in visual_anchors}
    anchors = list(visual_anchors)
    for index, polity in enumerate(polities):
        if polity["stem"] in visual_stems:
            continue
        mask = own == index
        if int(mask.sum()) < 20:
            continue
        interior = distance_transform_edt(mask)
        py, px = np.unravel_index(int(np.argmax(interior)), interior.shape)
        anchors.append((polity, float(xs[px]), float(ys[py])))
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
    if not LOCAL_BASE_PLATE.is_file():
        raise SystemExit(
            f"Missing clean base plate: {LOCAL_BASE_PLATE}. "
            "Run EfolsMiradinsPact/tools/_render_galaxy_political_map.py first."
        )
    image = Image.open(LOCAL_BASE_PLATE).convert("RGBA")
    draw = ImageDraw.Draw(image)
    width, height = image.size
    scale = width / 1024

    for polity, x, y in _anchors(galaxy, image):
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

