from __future__ import annotations

import json
import logging
import time
from typing import Any

from aiokafka import AIOKafkaProducer

from app.config.settings import Settings, settings

logger = logging.getLogger(__name__)

_RECONNECT_INTERVAL_S = 30.0


class StormKafkaPublisher:
    """Async Kafka publisher for storm snapshots."""

    def __init__(self, app_settings: Settings):
        self._settings = app_settings
        self._producer: AIOKafkaProducer | None = None
        self._last_start_attempt: float | None = None

    @property
    def enabled(self) -> bool:
        return bool(self._settings.kafka_enabled and self._settings.kafka_bootstrap_servers)

    async def start(self) -> None:
        if not self.enabled:
            logger.info("Kafka publisher disabled")
            return
        self._last_start_attempt = time.monotonic()
        producer = AIOKafkaProducer(
            bootstrap_servers=self._settings.kafka_bootstrap_servers,
            acks="all",
            linger_ms=20,
        )
        try:
            await producer.start()
        except Exception:
            logger.exception(
                "Kafka producer failed to start (%s); continuing without Kafka",
                self._settings.kafka_bootstrap_servers,
            )
            try:
                await producer.stop()
            except Exception:
                pass
            self._producer = None
            return
        self._producer = producer
        logger.info(
            "Kafka publisher started bootstrap=%s topic=%s",
            self._settings.kafka_bootstrap_servers,
            self._settings.kafka_topic,
        )

    def _should_retry_start(self) -> bool:
        if not self.enabled or self._last_start_attempt is None:
            return False
        return time.monotonic() - self._last_start_attempt >= _RECONNECT_INTERVAL_S

    async def stop(self) -> None:
        self._last_start_attempt = None
        if not self._producer:
            return
        try:
            await self._producer.stop()
        except Exception:
            logger.exception("Kafka producer stop failed")
        finally:
            self._producer = None

    async def publish_snapshot(self, payload: dict[str, Any]) -> None:
        """Publish snapshot; swallow errors so WS path stays healthy."""
        if not self._producer and self._should_retry_start():
            await self.start()
        if not self._producer:
            return
        try:
            key = str(payload.get("tick", "")).encode("utf-8")
            value = json.dumps(payload, ensure_ascii=False).encode("utf-8")
            await self._producer.send_and_wait(
                self._settings.kafka_topic,
                value=value,
                key=key,
            )
        except Exception:
            logger.exception("Kafka publish failed for tick=%s", payload.get("tick"))


storm_kafka = StormKafkaPublisher(settings)
