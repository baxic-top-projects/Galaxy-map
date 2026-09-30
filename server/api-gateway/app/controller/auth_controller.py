from __future__ import annotations

import json

from fastapi import APIRouter, Request, Response

from app.config.settings import settings
from app.service.auth_client_service import auth_client


router = APIRouter(prefix="/api/v1/auth", tags=["auth"])


def _forward_headers(request: Request) -> dict[str, str]:
    headers: dict[str, str] = {}
    for name in ("authorization", "content-type", "cookie", "user-agent"):
        value = request.headers.get(name)
        if value:
            headers[name] = value
    return headers


def _proxy_response(upstream) -> Response:
    headers: dict[str, str] = {}
    for name in ("location", "cache-control"):
        value = upstream.headers.get(name)
        if value:
            headers[name] = value
    response = Response(
        content=upstream.content,
        status_code=upstream.status_code,
        media_type=upstream.headers.get("content-type", "application/json"),
        headers=headers,
    )
    for cookie in upstream.headers.get_list("set-cookie"):
        response.headers.append(
            "set-cookie",
            cookie.replace("Path=/internal/v1/auth", "Path=/api/v1/auth"),
        )
    return response


@router.api_route(
    "/{path:path}",
    methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
)
async def proxy_auth(path: str, request: Request) -> Response:
    body = await request.body()
    headers = _forward_headers(request)
    if path in {"refresh", "logout"} and not body:
        refresh_token = request.cookies.get("galaxy_refresh_token")
        if refresh_token:
            body = json.dumps({"refresh_token": refresh_token}).encode()
            headers["content-type"] = "application/json"
    upstream = await auth_client.request(
        request.method,
        f"/internal/v1/auth/{path}",
        headers=headers,
        params=dict(request.query_params),
        content=body or None,
    )
    response = _proxy_response(upstream)
    if upstream.status_code < 400 and path in {
        "register",
        "login",
        "refresh",
        "exchange-code",
    }:
        try:
            payload = upstream.json()
        except (ValueError, json.JSONDecodeError):
            return response
        refresh_token = payload.pop("refresh_token", None)
        if refresh_token:
            response = Response(
                content=json.dumps(payload),
                status_code=upstream.status_code,
                media_type="application/json",
            )
            response.set_cookie(
                "galaxy_refresh_token",
                refresh_token,
                max_age=settings.refresh_cookie_max_age,
                httponly=True,
                secure=settings.refresh_cookie_secure,
                samesite="lax",
                path="/api/v1/auth",
                domain=settings.refresh_cookie_domain or None,
            )
    if upstream.status_code < 400 and path == "logout":
        response.delete_cookie(
            "galaxy_refresh_token",
            path="/api/v1/auth",
            domain=settings.refresh_cookie_domain or None,
        )
    return response
