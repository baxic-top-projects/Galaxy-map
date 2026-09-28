from __future__ import annotations

from fastapi import APIRouter

from app.dto.health import GatewayHealthDto
from app.service.asset_client_service import asset_client
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
        assets_ok = assets.status_code == 200 and asset_body.get("status") == "ok"
    except Exception as exc:  # noqa: BLE001
        asset_payload = {"statusCode": 0, "error": str(exc)}
        assets_ok = False

    storm_ok = storm.status_code == 200
    status = "ok" if storm_ok and assets_ok else "degraded"
    return GatewayHealthDto(
        status=status,
        service="api-gateway",
        stormService={"statusCode": storm.status_code, "body": storm_body},
        assetService=asset_payload,
    )
