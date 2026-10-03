from __future__ import annotations

import logging
import time
from typing import Any

import httpx

from app.config.settings import Settings

logger = logging.getLogger(__name__)


def fetch_galaxy_index(settings: Settings, *, attempts: int = 40, delay_seconds: float = 3.0) -> dict[str, Any]:
    """Load galaxy graph payload from catalog-service (Postgres-backed)."""
    base_url = settings.catalog_service_url.rstrip("/")
    # The lean graph endpoint keeps startup memory low; the full index is only a
    # fallback for catalog builds that predate it.
    graph_url = f"{base_url}/internal/v1/galaxy/graph"
    index_url = f"{base_url}/internal/v1/galaxy"
    last_error: Exception | None = None
    for attempt in range(1, attempts + 1):
        try:
            with httpx.Client(timeout=settings.catalog_timeout_seconds) as client:
                response = client.get(graph_url)
                if response.status_code == 404:
                    response = client.get(index_url)
                response.raise_for_status()
                payload = response.json()
            systems = payload.get("systems") or []
            if not systems:
                raise RuntimeError("Catalog galaxy index has no systems yet")
            logger.info("Loaded galaxy graph from catalog (%s systems)", len(systems))
            return payload
        except Exception as exc:  # noqa: BLE001
            last_error = exc
            logger.warning(
                "Catalog galaxy fetch failed (%s/%s): %s",
                attempt,
                attempts,
                exc,
            )
            if attempt < attempts:
                time.sleep(delay_seconds)
    raise RuntimeError(f"Unable to load galaxy graph from catalog: {last_error}")
