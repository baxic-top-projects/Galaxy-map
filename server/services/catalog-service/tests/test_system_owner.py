from __future__ import annotations

from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from app.service import catalog_query_service as query_module
from app.service.catalog_cache_service import CatalogCacheService
from app.service.catalog_query_service import (
    CatalogQueryService,
    _apply_galaxy_ownership,
    _apply_system_ownership,
)


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


def test_visual_ownership_outranks_catalog_stem(monkeypatch):
    monkeypatch.setattr(
        query_module,
        "VISUAL_OWNERSHIP",
        {"A:One": "Extragroks"},
    )
    payload = _apply_system_ownership({"id": "A:One", "stem": "Cyberlins"})
    assert payload["stem"] == "Extragroks"
    assert payload["canonicalStem"] == "Cyberlins"


def test_manual_ownership_outranks_visual_map(monkeypatch):
    monkeypatch.setattr(
        query_module,
        "VISUAL_OWNERSHIP",
        {"A:One": "Extragroks"},
    )
    payload = _apply_system_ownership(
        {"id": "A:One", "stem": "Cyberlins"},
        manual={"A:One": "Miradin_Empire"},
    )
    assert payload["stem"] == "Miradin_Empire"
    assert payload["canonicalStem"] == "Cyberlins"


def test_galaxy_ownership_updates_search_entries(monkeypatch):
    monkeypatch.setattr(
        query_module,
        "VISUAL_OWNERSHIP",
        {"A:One": "Extragroks"},
    )
    galaxy = _apply_galaxy_ownership(
        {
            "systems": [{"id": "A:One", "stem": "Cyberlins"}],
            "search": [{"id": "A:One", "stem": "Cyberlins", "kind": "system"}],
        },
        manual={"A:One": "Morat_Syndicate"},
    )
    assert galaxy["systems"][0]["stem"] == "Morat_Syndicate"
    assert galaxy["search"][0]["stem"] == "Morat_Syndicate"


def test_update_system_owner_persists_and_clears_cache(monkeypatch):
    redis = FakeRedis()
    cache = CatalogCacheService(client=redis)
    cache.set_json("galaxy", {"systems": []}, 60)
    catalog = CatalogQueryService(cache=cache)

    system = SimpleNamespace(
        id="A:One",
        kind="star",
        stem="Cyberlins",
        detail={"id": "A:One", "stem": "Cyberlins", "token": "One"},
    )
    polity = SimpleNamespace(stem="Miradin_Empire", payload={"stem": "Miradin_Empire"})
    overrides: dict[str, SimpleNamespace] = {}

    class FakeSession:
        def get(self, model, key):
            name = getattr(model, "__name__", str(model))
            if name == "SystemRow":
                return system if key == "A:One" else None
            if name == "PolityRow":
                return polity if key == "Miradin_Empire" else None
            if name == "SystemOwnerOverrideRow":
                return overrides.get(key)
            return None

        def add(self, row):
            overrides[row.system_id] = row

        def commit(self):
            return None

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

    monkeypatch.setattr(query_module, "SessionLocal", FakeSession)

    result = catalog.update_system_owner("A:One", "Miradin_Empire")
    assert result["stem"] == "Miradin_Empire"
    assert result["canonicalStem"] == "Cyberlins"
    assert overrides["A:One"].stem == "Miradin_Empire"
    assert cache.get_json("galaxy") is None


def test_assigning_unnamed_star_generates_name_and_planets(monkeypatch):
    catalog = CatalogQueryService(cache=CatalogCacheService(client=FakeRedis()))
    system = SimpleNamespace(
        id="frontier:arm-1:star-777",
        kind="star",
        stem=None,
        token="",
        name_en="",
        name_ru="",
        world_count=0,
        detail={
            "id": "frontier:arm-1:star-777",
            "kind": "star",
            "token": "",
            "nameEn": "",
            "nameRu": "",
            "worlds": [],
        },
    )
    polity = SimpleNamespace(stem="Veyran_Accord", payload={"stem": "Veyran_Accord"})
    added = []

    class FakeSession:
        def get(self, model, key):
            name = getattr(model, "__name__", str(model))
            if name == "SystemRow":
                return system
            if name == "PolityRow":
                return polity
            return None

        def add(self, row):
            added.append(row)

        def commit(self):
            return None

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

    monkeypatch.setattr(query_module, "SessionLocal", FakeSession)
    result = catalog.update_system_owner(system.id, polity.stem)

    assert result["stem"] == polity.stem
    assert result["token"]
    assert result["nameRu"]
    assert not result["nameRu"].startswith("Пограничная звезда")
    assert 1 <= len(result["worlds"]) <= 3
    assert system.world_count == len(result["worlds"])
    assert len(added) == 2 + len(result["worlds"])


def test_update_system_owner_rejects_axis_well(monkeypatch):
    catalog = CatalogQueryService(cache=CatalogCacheService(client=FakeRedis()))
    system = SimpleNamespace(id="AxisWell", kind="well", stem=None, detail={"id": "AxisWell"})

    class FakeSession:
        def get(self, model, key):
            name = getattr(model, "__name__", str(model))
            if name == "SystemRow":
                return system
            return None

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

    monkeypatch.setattr(query_module, "SessionLocal", FakeSession)
    with pytest.raises(HTTPException) as exc:
        catalog.update_system_owner("AxisWell", "Miradin_Empire")
    assert exc.value.status_code == 400
