from __future__ import annotations

import re
import time
from typing import Any
from urllib.parse import urljoin

import boto3
from botocore.client import Config
from fastapi import HTTPException

from app.config.settings import Settings, settings
from app.dto.asset import AssetItemDto, AssetKind, AssetManifestDto, AssetResolveDto

KIND_PREFIX = {
    "stars": "stars/",
    "planets": "planets/",
    "features": "features/",
}

NAME_PATTERNS = {
    "stars": re.compile(r"^star_type_(.+)\.glb$", re.IGNORECASE),
    "planets": re.compile(r"^planet_type_(.+)\.glb$", re.IGNORECASE),
    "features": re.compile(r"^system_feature_(.+)\.glb$", re.IGNORECASE),
}


class S3AssetService:
    """Lists GLB assets in S3 and builds browser-facing URLs (public or presigned)."""

    def __init__(self, app_settings: Settings | None = None):
        self.settings = app_settings or settings
        self._client = None
        self._cache: AssetManifestDto | None = None
        self._cache_at = 0.0

    def _ensure_client(self):
        if self._client is not None:
            return self._client
        if not self.settings.s3_access_key_id or not self.settings.s3_secret_access_key:
            raise HTTPException(
                status_code=503,
                detail="S3 credentials are not configured (ASSET_S3_ACCESS_KEY_ID / ASSET_S3_SECRET_ACCESS_KEY)",
            )
        kwargs: dict[str, Any] = {
            "service_name": "s3",
            "region_name": self.settings.s3_region,
            "aws_access_key_id": self.settings.s3_access_key_id,
            "aws_secret_access_key": self.settings.s3_secret_access_key,
            "config": Config(
                signature_version="s3v4",
                s3={"addressing_style": "path" if self.settings.s3_force_path_style else "auto"},
            ),
        }
        if self.settings.s3_endpoint_url:
            kwargs["endpoint_url"] = self.settings.s3_endpoint_url
        self._client = boto3.client(**kwargs)
        return self._client

    def health(self) -> dict[str, Any]:
        payload = {
            "status": "ok",
            "service": "asset-service",
            "bucket": self.settings.s3_bucket,
            "prefix": self.settings.s3_prefix,
            "presignEnabled": self.settings.presign_enabled,
            "configured": bool(self.settings.s3_access_key_id and self.settings.s3_secret_access_key),
        }
        if not payload["configured"]:
            payload["status"] = "degraded"
            return payload
        try:
            client = self._ensure_client()
            client.head_bucket(Bucket=self.settings.s3_bucket)
            payload["bucketReachable"] = True
        except Exception as exc:  # noqa: BLE001 - surface health without crashing
            payload["status"] = "degraded"
            payload["bucketReachable"] = False
            payload["error"] = str(exc)
        return payload

    def _public_url(self, object_key: str) -> str:
        base = (self.settings.s3_public_base_url or "").rstrip("/")
        if not base:
            # Fallback to path-style endpoint URL if provided.
            endpoint = (self.settings.s3_endpoint_url or "").rstrip("/")
            if endpoint:
                return f"{endpoint}/{self.settings.s3_bucket}/{object_key.lstrip('/')}"
            raise HTTPException(
                status_code=503,
                detail="ASSET_S3_PUBLIC_BASE_URL is required when presigning is disabled",
            )
        return f"{base}/{object_key.lstrip('/')}"

    def _object_url(self, object_key: str) -> str:
        if self.settings.presign_enabled:
            client = self._ensure_client()
            return client.generate_presigned_url(
                "get_object",
                Params={"Bucket": self.settings.s3_bucket, "Key": object_key},
                ExpiresIn=self.settings.presign_ttl_seconds,
            )
        return self._public_url(object_key)

    def _preview_key(self, object_key: str) -> str | None:
        if not object_key.lower().endswith(".glb"):
            return None
        return object_key[: -len(".glb")] + "_preview.png"

    def _parse_item(self, object_key: str) -> AssetItemDto | None:
        prefix = self.settings.s3_prefix.lstrip("/")
        relative = object_key
        if prefix and object_key.startswith(prefix):
            relative = object_key[len(prefix) :]
        relative = relative.lstrip("/")
        for kind, kind_prefix in KIND_PREFIX.items():
            if not relative.startswith(kind_prefix):
                continue
            filename = relative[len(kind_prefix) :]
            match = NAME_PATTERNS[kind].match(filename)
            if not match:
                return None
            key = match.group(1)
            preview_key = self._preview_key(object_key)
            return AssetItemDto(
                kind=kind,  # type: ignore[arg-type]
                key=key,
                objectKey=object_key,
                url=self._object_url(object_key),
                previewUrl=self._object_url(preview_key) if preview_key else None,
            )
        return None

    def list_objects(self) -> list[str]:
        client = self._ensure_client()
        keys: list[str] = []
        token = None
        while True:
            kwargs: dict[str, Any] = {
                "Bucket": self.settings.s3_bucket,
                "Prefix": self.settings.s3_prefix,
            }
            if token:
                kwargs["ContinuationToken"] = token
            response = client.list_objects_v2(**kwargs)
            for item in response.get("Contents") or []:
                key = item.get("Key")
                if key and not key.endswith("/") and key.lower().endswith(".glb"):
                    keys.append(key)
            if not response.get("IsTruncated"):
                break
            token = response.get("NextContinuationToken")
        return keys

    def manifest(self, *, force: bool = False) -> AssetManifestDto:
        now = time.monotonic()
        if (
            not force
            and self._cache is not None
            and now - self._cache_at < self.settings.manifest_cache_seconds
        ):
            return self._cache

        stars: list[AssetItemDto] = []
        planets: list[AssetItemDto] = []
        features: list[AssetItemDto] = []
        for object_key in self.list_objects():
            item = self._parse_item(object_key)
            if item is None:
                continue
            if item.kind == "stars":
                stars.append(item)
            elif item.kind == "planets":
                planets.append(item)
            else:
                features.append(item)

        stars.sort(key=lambda row: row.key)
        planets.sort(key=lambda row: row.key)
        features.sort(key=lambda row: row.key)

        payload = AssetManifestDto(
            bucket=self.settings.s3_bucket,
            prefix=self.settings.s3_prefix,
            publicBaseUrl=(self.settings.s3_public_base_url or "").rstrip("/"),
            presigned=self.settings.presign_enabled,
            stars=stars,
            planets=planets,
            features=features,
        )
        self._cache = payload
        self._cache_at = now
        return payload

    def resolve(self, kind: AssetKind, key: str) -> AssetResolveDto:
        manifest = self.manifest()
        pool = {"stars": manifest.stars, "planets": manifest.planets, "features": manifest.features}[kind]
        for item in pool:
            if item.key == key:
                return AssetResolveDto(
                    kind=item.kind,
                    key=item.key,
                    objectKey=item.objectKey,
                    url=item.url,
                    previewUrl=item.previewUrl,
                )
        # Synthesize expected object key even if listing missed it (lazy public URL).
        filename = {
            "stars": f"star_type_{key}.glb",
            "planets": f"planet_type_{key}.glb",
            "features": f"system_feature_{key}.glb",
        }[kind]
        object_key = f"{self.settings.s3_prefix.rstrip('/')}/{KIND_PREFIX[kind]}{filename}".replace("//", "/")
        preview_key = self._preview_key(object_key)
        return AssetResolveDto(
            kind=kind,
            key=key,
            objectKey=object_key,
            url=self._object_url(object_key),
            previewUrl=self._object_url(preview_key) if preview_key else None,
        )


asset_service = S3AssetService()
