from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient
import httpx
import pytest

from app import main as gateway
from app.service import asset_client_service, storm_client_service


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


def test_gateway_proxies_storm_and_asset_endpoints(monkeypatch, storm_backend, asset_backend):
    storm_transport = httpx.ASGITransport(app=storm_backend)
    asset_transport = httpx.ASGITransport(app=asset_backend)

    class FakeStormClient(httpx.AsyncClient):
        def __init__(self, *args, **kwargs):
            kwargs["transport"] = storm_transport
            kwargs["base_url"] = "http://storm-service"
            super().__init__(*args, **kwargs)

    class FakeAssetClient(httpx.AsyncClient):
        def __init__(self, *args, **kwargs):
            kwargs["transport"] = asset_transport
            kwargs["base_url"] = "http://asset-service"
            super().__init__(*args, **kwargs)

    monkeypatch.setattr(storm_client_service.httpx, "AsyncClient", FakeStormClient)
    monkeypatch.setattr(storm_client_service.settings, "storm_service_url", "http://storm-service")
    monkeypatch.setattr(
        storm_client_service,
        "storm_client",
        storm_client_service.StormClientService("http://storm-service"),
    )
    monkeypatch.setattr(
        "app.controller.storm_controller.storm_client",
        storm_client_service.storm_client,
    )
    monkeypatch.setattr(
        "app.controller.health_controller.storm_client",
        storm_client_service.storm_client,
    )

    monkeypatch.setattr(asset_client_service.httpx, "AsyncClient", FakeAssetClient)
    monkeypatch.setattr(asset_client_service.settings, "asset_service_url", "http://asset-service")
    monkeypatch.setattr(
        asset_client_service,
        "asset_client",
        asset_client_service.AssetClientService("http://asset-service"),
    )
    monkeypatch.setattr(
        "app.controller.asset_controller.asset_client",
        asset_client_service.asset_client,
    )
    monkeypatch.setattr(
        "app.controller.health_controller.asset_client",
        asset_client_service.asset_client,
    )

    client = TestClient(gateway.app)
    health = client.get("/health")
    assert health.status_code == 200
    assert health.json()["status"] == "ok"
    assert health.json()["stormService"]["body"]["service"] == "storm-service"
    assert health.json()["assetService"]["body"]["service"] == "asset-service"

    storms = client.get("/api/v1/storms")
    assert storms.status_code == 200
    payload = storms.json()
    assert payload["systems"][0]["systemId"] == "A:One"

    one = client.get("/api/v1/storms/systems/A:One")
    assert one.status_code == 200
    assert one.json()["active"] is True

    manifest = client.get("/api/v1/assets/manifest")
    assert manifest.status_code == 200
    assert manifest.json()["stars"][0]["key"] == "class_g"
