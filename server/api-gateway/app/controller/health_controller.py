from __future__ import annotations

from fastapi import APIRouter

from app.dto.health import GatewayHealthDto
from app.service.storm_client_service import storm_client

router = APIRouter()


@router.get("/health", response_model=GatewayHealthDto)
async def health() -> GatewayHealthDto:
    storm = await storm_client.request("GET", "/health")
    body = storm.json() if "application/json" in storm.headers.get("content-type", "") else {}
    return GatewayHealthDto(
        status="ok" if storm.status_code == 200 else "degraded",
        service="api-gateway",
        stormService={"statusCode": storm.status_code, "body": body},
    )
