from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

StormType = Literal["electric", "gravity", "particle", "shroud"]
StormStage = Literal["forming", "active", "dissipating"]


class AffectedSystemDto(BaseModel):
    systemId: str
    intensity: float = Field(ge=0.0, le=1.0)
    hopsFromOrigin: int = Field(ge=0)


class StormDto(BaseModel):
    id: str
    type: StormType
    stage: StormStage
    originSystemId: str
    intensity: float = Field(ge=0.0, le=1.0)
    radiusHops: int = Field(ge=0)
    ageTicks: int = Field(ge=0)
    color: str
    affectedSystems: list[AffectedSystemDto] = Field(default_factory=list)


class SystemStormStateDto(BaseModel):
    systemId: str
    intensity: float = Field(ge=0.0, le=1.0)
    stage: StormStage
    type: StormType
    stormId: str
    color: str


class StormSnapshotDto(BaseModel):
    tick: int
    generatedAt: str
    storms: list[StormDto]
    systems: list[SystemStormStateDto]


class SystemStormResponseDto(BaseModel):
    systemId: str
    active: bool
    storm: SystemStormStateDto | None = None
