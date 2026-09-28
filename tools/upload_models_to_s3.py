"""Upload models + type textures into the configured S3/Yandex bucket."""

from __future__ import annotations

import mimetypes
import sys
from pathlib import Path

import boto3
from botocore.client import Config

try:
    from dotenv import dotenv_values
except ImportError:  # pragma: no cover
    def dotenv_values(path):  # type: ignore[misc]
        values = {}
        for line in Path(path).read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            values[key.strip()] = value.strip()
        return values

ROOT = Path(__file__).resolve().parents[1]
PUBLIC_DIR = ROOT / "client" / "public"
ENV_PATH = ROOT / "server" / "services" / "asset-service" / ".env"

UPLOAD_ROOTS = (
    (PUBLIC_DIR / "models", "models"),
    (PUBLIC_DIR / "textures" / "star_types", "textures/star_types"),
    (PUBLIC_DIR / "textures" / "planet_types", "textures/planet_types"),
    (PUBLIC_DIR / "textures" / "system_features", "textures/system_features"),
)

ROOT_TEXTURE_FILES = (
    "galaxy_territory_plate.png",
    "galaxy_political_map.png",
    "galaxy_base_plate.png",
    "system_starfield.png",
)


def upload_tree(client, bucket: str, local_dir: Path, key_prefix: str) -> int:
    if not local_dir.is_dir():
        print(f"skip missing {local_dir}")
        return 0
    files = [path for path in local_dir.rglob("*") if path.is_file()]
    count = 0
    for path in sorted(files):
        relative = path.relative_to(local_dir).as_posix()
        key = f"{key_prefix.strip('/')}/{relative}"
        content_type = mimetypes.guess_type(path.name)[0]
        if path.suffix.lower() == ".glb":
            content_type = "model/gltf-binary"
        extra = {"ContentType": content_type or "application/octet-stream"}
        try:
            client.upload_file(str(path), bucket, key, ExtraArgs={**extra, "ACL": "public-read"})
        except Exception:
            client.upload_file(str(path), bucket, key, ExtraArgs=extra)
        count += 1
        size_mb = path.stat().st_size / (1024 * 1024)
        print(f"[{count}] s3://{bucket}/{key} ({size_mb:.1f} MB)")
    return count


def main() -> int:
    env = dotenv_values(ENV_PATH)
    bucket = env.get("ASSET_S3_BUCKET") or "galaxy-map-assets"
    region = env.get("ASSET_S3_REGION") or "ru-central1"
    endpoint = env.get("ASSET_S3_ENDPOINT_URL") or None
    access_key = env.get("ASSET_S3_ACCESS_KEY_ID") or ""
    secret_key = env.get("ASSET_S3_SECRET_ACCESS_KEY") or ""
    if not access_key or not secret_key:
        print("Missing ASSET_S3_ACCESS_KEY_ID / ASSET_S3_SECRET_ACCESS_KEY", file=sys.stderr)
        return 1

    client = boto3.client(
        "s3",
        region_name=region,
        endpoint_url=endpoint or None,
        aws_access_key_id=access_key,
        aws_secret_access_key=secret_key,
        config=Config(signature_version="s3v4"),
    )

    total = 0
    for local_dir, prefix in UPLOAD_ROOTS:
        print(f"==> {local_dir} -> {prefix}/")
        total += upload_tree(client, bucket, local_dir, prefix)

    textures_dir = PUBLIC_DIR / "textures"
    print(f"==> root map textures -> textures/")
    for name in ROOT_TEXTURE_FILES:
        path = textures_dir / name
        if not path.is_file():
            print(f"skip missing {path}")
            continue
        key = f"textures/{name}"
        content_type = mimetypes.guess_type(path.name)[0] or "image/png"
        extra = {"ContentType": content_type}
        try:
            client.upload_file(str(path), bucket, key, ExtraArgs={**extra, "ACL": "public-read"})
        except Exception:
            client.upload_file(str(path), bucket, key, ExtraArgs=extra)
        total += 1
        size_mb = path.stat().st_size / (1024 * 1024)
        print(f"[root] s3://{bucket}/{key} ({size_mb:.1f} MB)")

    print(f"Done. Uploaded {total} objects.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
