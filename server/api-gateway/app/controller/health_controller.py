from __future__ import annotations

from fastapi import APIRouter

from app.dto.health import GatewayHealthDto
from app.service.asset_client_service import asset_client
from app.service.catalog_client_service import catalog_client
from app.service.storm_client_service import storm_client

router = APIRouter()


@router.get("/health", response_model=GatewayHealthDto)
async def health() -> GatewayHealthDto:
    storm = await storm_client.request("GET", "/health")
    storm_body = storm.json() if "application/json" in storm.headers.get("content-type", "") else {}

    try:
        assets = await asset_client.request("GET", "/health")
        asset_body = assets.json() if "application/json" in assets.headers.get("content-type", "") else {}
        asset_payload = {"statusCode": assets.status_code, "body": asset_body}
        assets_ok = assets.status_code == 200 and asset_body.get("status") in {"ok", "empty", "degraded"}
    except Exception as exc:  # noqa: BLE001
        asset_payload = {"statusCode": 0, "error": str(exc)}
        assets_ok = False

    try:
        catalog = await catalog_client.request("GET", "/health")
        catalog_body = catalog.json() if "application/json" in catalog.headers.get("content-type", "") else {}
        catalog_payload = {"statusCode": catalog.status_code, "body": catalog_body}
        catalog_ok = catalog.status_code == 200 and catalog_body.get("status") in {"ok", "empty"}
    except Exception as exc:  # noqa: BLE001
        catalog_payload = {"statusCode": 0, "error": str(exc)}
        catalog_ok = False

    storm_ok = storm.status_code == 200
    status = "ok" if storm_ok and assets_ok and catalog_ok else "degraded"
    return GatewayHealthDto(
        status=status,
        service="api-gateway",
        stormService={"statusCode": storm.status_code, "body": storm_body},
        assetService=asset_payload,
        catalogService=catalog_payload,
    )
