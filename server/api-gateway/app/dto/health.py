from __future__ import annotations

from pydantic import BaseModel, Field


class GatewayHealthDto(BaseModel):
    status: str
    service: str
    stormService: dict
    assetService: dict = Field(default_factory=dict)
