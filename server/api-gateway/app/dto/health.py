from __future__ import annotations

from pydantic import BaseModel


class GatewayHealthDto(BaseModel):
    status: str
    service: str
    stormService: dict
