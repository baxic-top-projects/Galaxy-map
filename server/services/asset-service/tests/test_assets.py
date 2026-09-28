from __future__ import annotations

from app.config.settings import Settings
from app.service.s3_asset_service import S3AssetService


def test_parse_star_and_planet_keys(monkeypatch):
    settings = Settings(
        s3_bucket="test-bucket",
        s3_public_base_url="https://cdn.example/test-bucket",
        s3_prefix="models/",
        s3_access_key_id="x",
        s3_secret_access_key="y",
        presign_enabled=False,
    )
    service = S3AssetService(settings)

    star = service._parse_item("models/stars/star_type_class_g.glb")
    assert star is not None
    assert star.kind == "stars"
    assert star.key == "class_g"
    assert star.url == "https://cdn.example/test-bucket/models/stars/star_type_class_g.glb"
    assert star.previewUrl.endswith("star_type_class_g_preview.png")

    planet = service._parse_item("models/planets/planet_type_continental.glb")
    assert planet is not None
    assert planet.kind == "planets"
    assert planet.key == "continental"

    feature = service._parse_item("models/features/system_feature_asteroid_belt.glb")
    assert feature is not None
    assert feature.kind == "features"
    assert feature.key == "asteroid_belt"


def test_manifest_uses_listed_keys(monkeypatch):
    settings = Settings(
        s3_bucket="test-bucket",
        s3_public_base_url="https://cdn.example/test-bucket",
        s3_prefix="models/",
        s3_access_key_id="x",
        s3_secret_access_key="y",
        presign_enabled=False,
        manifest_cache_seconds=0,
    )
    service = S3AssetService(settings)
    monkeypatch.setattr(
        service,
        "list_objects",
        lambda: [
            "models/stars/star_type_class_m.glb",
            "models/planets/planet_type_ocean.glb",
            "models/features/system_feature_asteroid_belt.glb",
            "models/readme.txt",
        ],
    )
    manifest = service.manifest(force=True)
    assert [row.key for row in manifest.stars] == ["class_m"]
    assert [row.key for row in manifest.planets] == ["ocean"]
    assert [row.key for row in manifest.features] == ["asteroid_belt"]
    assert manifest.presigned is False
