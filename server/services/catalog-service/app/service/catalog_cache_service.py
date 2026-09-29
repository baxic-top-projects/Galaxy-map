from __future__ import annotations

import json
import logging
from typing import Any

from redis import Redis
from redis.exceptions import RedisError

from app.config.settings import settings

logger = logging.getLogger(__name__)


class CatalogCacheService:
    """Small fail-open JSON cache for catalog responses."""

    namespace = "catalog:v1"

    def __init__(self, url: str = "", client: Redis | None = None):
        self._enabled = bool(url or client)
        self._client = client
        if self._client is None and url:
            self._client = Redis.from_url(
                url,
                decode_responses=True,
                socket_connect_timeout=0.5,
                socket_timeout=0.5,
                health_check_interval=30,
            )

    @property
    def enabled(self) -> bool:
        return self._enabled

    def get_json(self, key: str) -> Any | None:
        if self._client is None:
            return None
        try:
            value = self._client.get(f"{self.namespace}:{key}")
            return json.loads(value) if value is not None else None
        except (RedisError, ValueError, TypeError) as exc:
            logger.warning("Redis cache read failed for %s: %s", key, exc)
            return None

    def set_json(self, key: str, value: Any, ttl_seconds: int) -> None:
        if self._client is None:
            return
        try:
            self._client.set(
                f"{self.namespace}:{key}",
                json.dumps(value, ensure_ascii=False, separators=(",", ":")),
                ex=max(1, ttl_seconds),
            )
        except (RedisError, TypeError, ValueError) as exc:
            logger.warning("Redis cache write failed for %s: %s", key, exc)

    def clear(self) -> None:
        if self._client is None:
            return
        try:
            keys = list(self._client.scan_iter(match=f"{self.namespace}:*"))
            if keys:
                self._client.delete(*keys)
        except RedisError as exc:
            logger.warning("Redis cache invalidation failed: %s", exc)

    def status(self) -> str:
        if self._client is None:
            return "disabled"
        try:
            return "ok" if self._client.ping() else "error"
        except RedisError:
            return "error"


catalog_cache = CatalogCacheService(settings.redis_url)
