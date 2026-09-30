from __future__ import annotations

from app.service.catalog_cache_service import CatalogCacheService
from app.service.catalog_query_service import CatalogQueryService


class FakeRedis:
    def __init__(self):
        self.values: dict[str, str] = {}

    def get(self, key: str):
        return self.values.get(key)

    def set(self, key: str, value: str, ex: int):
        assert ex > 0
        self.values[key] = value

    def scan_iter(self, match: str):
        prefix = match.removesuffix("*")
        return (key for key in list(self.values) if key.startswith(prefix))

    def delete(self, *keys: str):
        for key in keys:
            self.values.pop(key, None)

    def ping(self):
        return True


def test_cache_round_trip_and_clear():
    client = FakeRedis()
    cache = CatalogCacheService(client=client)

    cache.set_json("galaxy", {"name": "Галактика"}, 60)
    assert cache.get_json("galaxy") == {"name": "Галактика"}
    assert cache.status() == "ok"

    cache.clear()
    assert cache.get_json("galaxy") is None


def test_cache_does_not_restore_stale_value_after_clear():
    cache = CatalogCacheService(client=FakeRedis())
    generation = cache.generation

    cache.clear()
    cache.set_json(
        "galaxy",
        {"systems": [{"id": "stale"}]},
        60,
        expected_generation=generation,
    )

    assert cache.get_json("galaxy") is None


def test_catalog_uses_cached_payload_without_database(monkeypatch):
    cache = CatalogCacheService(client=FakeRedis())
    cache.set_json("galaxy", {"systems": [{"id": "cached"}]}, 60)
    cache.set_json("system:id:cached", {"id": "cached", "worlds": []}, 60)
    catalog = CatalogQueryService(cache=cache)

    class FakeSession:
        def scalars(self, _statement):
            return []

        def get(self, _model, _key):
            return None

        def rollback(self):
            return None

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

    monkeypatch.setattr(
        "app.service.catalog_query_service.SessionLocal",
        FakeSession,
    )

    assert catalog.get_galaxy_index()["systems"][0]["id"] == "cached"
    assert catalog.get_system_by_id("cached")["id"] == "cached"
