from __future__ import annotations

import io
import uuid

import boto3
import httpx
from fastapi import HTTPException, UploadFile

from app.config import settings


CONTENT_EXTENSIONS = {
    "image/jpeg": "jpg",
    "image/png": "png",
    "image/webp": "webp",
}


def _client():
    if not settings.s3_bucket:
        raise HTTPException(status_code=503, detail="Avatar storage is not configured")
    return boto3.client(
        "s3",
        endpoint_url=settings.s3_endpoint_url or None,
        region_name=settings.s3_region,
        aws_access_key_id=settings.s3_access_key_id or None,
        aws_secret_access_key=settings.s3_secret_access_key.get_secret_value() or None,
    )


def _url(key: str) -> str:
    if settings.s3_public_base_url:
        return f"{settings.s3_public_base_url.rstrip('/')}/{key}"
    return f"{settings.s3_endpoint_url.rstrip('/')}/{settings.s3_bucket}/{key}"


def put_bytes(user_id: str, data: bytes, content_type: str) -> tuple[str, str]:
    extension = CONTENT_EXTENSIONS.get(content_type)
    if extension is None:
        raise HTTPException(status_code=400, detail="Avatar must be PNG, JPEG or WebP")
    if not data or len(data) > settings.avatar_max_bytes:
        raise HTTPException(status_code=400, detail="Avatar exceeds the 5 MB limit")
    prefix = settings.s3_avatar_prefix.strip("/")
    key = f"{prefix}/{user_id}/{uuid.uuid4().hex}.{extension}"
    _client().put_object(
        Bucket=settings.s3_bucket,
        Key=key,
        Body=io.BytesIO(data),
        ContentType=content_type,
        CacheControl="public, max-age=31536000, immutable",
    )
    return key, _url(key)


async def put_upload(user_id: str, file: UploadFile) -> tuple[str, str]:
    data = await file.read(settings.avatar_max_bytes + 1)
    return put_bytes(user_id, data, file.content_type or "")


async def import_google_avatar(user_id: str, source_url: str) -> tuple[str, str] | None:
    try:
        async with httpx.AsyncClient(timeout=10, follow_redirects=True) as client:
            response = await client.get(source_url)
            response.raise_for_status()
        content_type = response.headers.get("content-type", "").split(";", 1)[0]
        return put_bytes(user_id, response.content, content_type)
    except Exception:
        return None


def delete(key: str | None) -> None:
    if not key or not settings.s3_bucket:
        return
    _client().delete_object(Bucket=settings.s3_bucket, Key=key)
