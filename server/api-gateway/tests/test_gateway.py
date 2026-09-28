from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient
import pytest

from app import main as gateway
from app.service import asset_client_service, catalog_client_service, storm_client_service


@pytest.fixture()
def storm_backend():
    backend = FastAPI()

    @backend.get("/health")
    def health():
        return {"status": "ok", "service": "storm-service", "tick": 3, "stormCount": 1}

    @backend.get("/internal/v1/storms")
    def storms():
        return {
            "tick": 3,
            "generatedAt": "2026-09-28T00:00:00+00:00",
            "storms": [],
            "systems": [
                {
                    "systemId": "A:One",
                    "intensity": 0.8,
                    "stage": "active",
                    "type": "electric",
                    "stormId": "storm-1",
                    "color": "#6ec8ff",
                }
            ],
        }

    @backend.get("/internal/v1/storms/systems/{system_id:path}")
    def system_storm(system_id: str):
        return {
            "systemId": system_id,
            "active": True,
            "storm": {
                "systemId": system_id,
                "intensity": 0.8,
                "stage": "active",
                "type": "electric",
                "stormId": "storm-1",
                "color": "#6ec8ff",
            },
        }

    return backend


@pytest.fixture()
def asset_backend():
    backend = FastAPI()

    @backend.get("/health")
    def health():
        return {
            "status": "ok",
            "service": "asset-service",
            "bucket": "galaxy-map-assets",
            "configured": True,
            "bucketReachable": True,
        }

    @backend.get("/internal/v1/assets/manifest")
    def manifest():
        return {
            "bucket": "galaxy-map-assets",
            "prefix": "models/",
            "publicBaseUrl": "https://cdn.example/galaxy-map-assets",
            "presigned": False,
            "stars": [
                {
                    "kind": "stars",
                    "key": "class_g",
                    "objectKey": "models/stars/star_type_class_g.glb",
                    "url": "https://cdn.example/galaxy-map-assets/models/stars/star_type_class_g.glb",
                    "previewUrl": None,
                }
            ],
            "planets": [],
            "features": [],
        }

    return backend


@pytest.fixture()
def catalog_backend():
    backend = FastAPI()

    @backend.get("/health")
    def health():
        return {"status": "ok", "service": "catalog-service", "hasSystems": True}

    @backend.get("/internal/v1/galaxy")
    def galaxy():
        return {
            "meta": {"source": "EfolsMiradinsPact"},
            "polities": [],
            "systems": [
                {
                    "id": "Miradin_Empire:MiradinSirius",
                    "token": "MiradinSirius",
                    "shard": "systems/Miradin_Empire__MiradinSirius.json",
                }
            ],
            "edgesCanon": [],
            "edgesDisplay": [],
            "search": [],
        }

    @backend.get("/internal/v1/systems/{system_id:path}")
    def system(system_id: str):
        return {"id": system_id, "token": "MiradinSirius", "worlds": []}

    return backend


def _backend_request(app: FastAPI, method: str, path: str):
    with TestClient(app) as client:
        return client.request(method, path)


def _patch_clients(monkeypatch, *, storm_backend, asset_backend, catalog_backend):
    async def storm_request(method: str, path: str):
        return _backend_request(storm_backend, method, path)

    async def asset_request(method: str, path: str):
        return _backend_request(asset_backend, method, path)

    async def catalog_request(method: str, path: str):
        return _backend_request(catalog_backend, method, path)

    monkeypatch.setattr(storm_client_service.storm_client, "request", storm_request)
    monkeypatch.setattr(asset_client_service.asset_client, "request", asset_request)
    monkeypatch.setattr(catalog_client_service.catalog_client, "request", catalog_request)
    monkeypatch.setattr("app.controller.storm_controller.storm_client", storm_client_service.storm_client)
    monkeypatch.setattr("app.controller.asset_controller.asset_client", asset_client_service.asset_client)
    monkeypatch.setattr("app.controller.catalog_controller.catalog_client", catalog_client_service.catalog_client)
    monkeypatch.setattr("app.controller.health_controller.storm_client", storm_client_service.storm_client)
    monkeypatch.setattr("app.controller.health_controller.asset_client", asset_client_service.asset_client)
    monkeypatch.setattr("app.controller.health_controller.catalog_client", catalog_client_service.catalog_client)


def test_gateway_proxies_storm_asset_and_catalog(monkeypatch, storm_backend, asset_backend, catalog_backend):
    _patch_clients(
        monkeypatch,
        storm_backend=storm_backend,
        asset_backend=asset_backend,
        catalog_backend=catalog_backend,
    )

    client = TestClient(gateway.app)
    health = client.get("/health")
    assert health.status_code == 200
    assert health.json()["status"] == "ok"
    assert health.json()["stormService"]["body"]["service"] == "storm-service"
    assert health.json()["assetService"]["body"]["service"] == "asset-service"
    assert health.json()["catalogService"]["body"]["service"] == "catalog-service"

    storms = client.get("/api/v1/storms")
    assert storms.status_code == 200
    assert storms.json()["systems"][0]["systemId"] == "A:One"

    one = client.get("/api/v1/storms/systems/A:One")
    assert one.status_code == 200
    assert one.json()["active"] is True

    manifest = client.get("/api/v1/assets/manifest")
    assert manifest.status_code == 200
    assert manifest.json()["stars"][0]["key"] == "class_g"

    galaxy = client.get("/api/v1/galaxy")
    assert galaxy.status_code == 200
    assert galaxy.json()["systems"][0]["id"] == "Miradin_Empire:MiradinSirius"

    system = client.get("/api/v1/systems/Miradin_Empire:MiradinSirius")
    assert system.status_code == 200
    assert system.json()["token"] == "MiradinSirius"
