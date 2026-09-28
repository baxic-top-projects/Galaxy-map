from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

AssetKind = Literal["stars", "planets", "features"]


class AssetItemDto(BaseModel):
    kind: AssetKind
    key: str
    objectKey: str
    url: str
    previewUrl: str | None = None


class AssetManifestDto(BaseModel):
    bucket: str
    prefix: str
    publicBaseUrl: str
    presigned: bool
    stars: list[AssetItemDto] = Field(default_factory=list)
    planets: list[AssetItemDto] = Field(default_factory=list)
    features: list[AssetItemDto] = Field(default_factory=list)


class AssetResolveDto(BaseModel):
    kind: AssetKind
    key: str
    objectKey: str
    url: str
    previewUrl: str | None = None
