from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient
import httpx

from app import main as gateway
from app.service import storm_client_service


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


def test_gateway_proxies_storm_endpoints(monkeypatch, storm_backend):
    transport = httpx.ASGITransport(app=storm_backend)

    class FakeAsyncClient(httpx.AsyncClient):
        def __init__(self, *args, **kwargs):
            kwargs["transport"] = transport
            kwargs["base_url"] = "http://storm-service"
            super().__init__(*args, **kwargs)

    monkeypatch.setattr(storm_client_service.httpx, "AsyncClient", FakeAsyncClient)
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

    client = TestClient(gateway.app)
    health = client.get("/health")
    assert health.status_code == 200
    assert health.json()["status"] == "ok"
    assert health.json()["stormService"]["body"]["service"] == "storm-service"

    storms = client.get("/api/v1/storms")
    assert storms.status_code == 200
    payload = storms.json()
    assert payload["systems"][0]["systemId"] == "A:One"

    one = client.get("/api/v1/storms/systems/A:One")
    assert one.status_code == 200
    assert one.json()["active"] is True
