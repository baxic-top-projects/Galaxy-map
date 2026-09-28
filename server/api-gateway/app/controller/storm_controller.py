from __future__ import annotations

import asyncio

from fastapi import APIRouter, Response, WebSocket, WebSocketDisconnect
import websockets
from websockets.exceptions import ConnectionClosed

from app.config.settings import settings
from app.service.storm_client_service import storm_client
from app.service.storm_ws_url import storm_ws_url

router = APIRouter()


@router.get("/api/v1/storms")
async def list_storms():
    response = await storm_client.request("GET", "/internal/v1/storms")
    return Response(
        content=response.content,
        status_code=response.status_code,
        media_type="application/json",
    )


@router.get("/api/v1/storms/systems/{system_id:path}")
async def system_storm(system_id: str):
    response = await storm_client.request("GET", f"/internal/v1/storms/systems/{system_id}")
    return Response(
        content=response.content,
        status_code=response.status_code,
        media_type="application/json",
    )


@router.websocket("/api/v1/storms/ws")
async def storms_ws_proxy(client: WebSocket) -> None:
    """Public WebSocket that proxies live storm snapshots from storm-service."""
    await client.accept()
    upstream_url = storm_ws_url()
    try:
        async with websockets.connect(
            upstream_url,
            open_timeout=settings.request_timeout_seconds,
        ) as upstream:

            async def client_to_upstream() -> None:
                try:
                    while True:
                        message = await client.receive_text()
                        await upstream.send(message)
                except WebSocketDisconnect:
                    await upstream.close()

            async def upstream_to_client() -> None:
                try:
                    async for message in upstream:
                        await client.send_text(message)
                except ConnectionClosed:
                    await client.close()

            await asyncio.gather(client_to_upstream(), upstream_to_client())
    except Exception:
        try:
            await client.close()
        except Exception:
            pass
