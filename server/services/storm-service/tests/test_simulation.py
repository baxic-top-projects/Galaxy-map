from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.config.settings import Settings
from app.service.galaxy_graph_service import GalaxyGraphService
from app.service.storm_model_client import FEATURE_COLUMNS, build_spawn_features
from app.service.storm_simulation_service import StormSimulationService


@pytest.fixture()
def tiny_galaxy(tmp_path: Path) -> Path:
    payload = {
        "systems": [
            {"id": "A:One", "kind": "star", "x": 0.0, "y": 0.0, "z": 0.0},
            {"id": "A:Two", "kind": "star", "x": 0.1, "y": 0.0, "z": 0.0},
            {"id": "A:Three", "kind": "star", "x": 0.2, "y": 0.0, "z": 0.0},
            {"id": "A:Four", "kind": "star", "x": 0.3, "y": 0.0, "z": 0.0},
            {"id": "A:Five", "kind": "star", "x": 0.4, "y": 0.0, "z": 0.0},
            {"id": "A:Isle", "kind": "star", "x": 0.9, "y": 0.9, "z": 0.0},
        ],
        "edgesDisplay": [
            {"a": "A:One", "b": "A:Two"},
            {"a": "A:Two", "b": "A:Three"},
            {"a": "A:Three", "b": "A:Four"},
            {"a": "A:Four", "b": "A:Five"},
        ],
    }
    path = tmp_path / "galaxy-index.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def test_graph_spreads_only_along_hypercorridors(tiny_galaxy: Path):
    graph = GalaxyGraphService(tiny_galaxy)
    hops = graph.systems_within_hops("A:One", 2)
    assert hops == {"A:One": 0, "A:Two": 1, "A:Three": 2}
    assert "A:Isle" not in hops


def test_spawn_features_match_model_columns():
    features = build_spawn_features(
        tick=12,
        storms=[],
        systems=[],
        ticks_since_spawn=3,
        spawns_last_5_ticks=1,
    )
    assert list(features.keys()) == list(FEATURE_COLUMNS)
    assert features["tick"] == 12.0
    assert features["active_storm_count"] == 0.0
    assert features["ticks_since_spawn"] == 3.0
    assert features["spawns_last_5_ticks"] == 1.0


def test_storm_migrates_along_hyperlanes(tiny_galaxy: Path):
    settings = Settings(
        galaxy_index_path=tiny_galaxy,
        seed=7,
        tick_seconds=1,
        max_active_storms=1,
        spawn_chance=1.0,
        form_ticks=2,
        active_ticks=8,
        dissipate_ticks=2,
        max_radius_hops=1,
        move_interval_ticks=3,
        path_hops_min=2,
        path_hops_max=4,
        worker_processes=1,
        kafka_enabled=False,
        model_enabled=False,
        model_url="",
    )
    sim = StormSimulationService(GalaxyGraphService(tiny_galaxy), settings)

    first = sim.step()
    assert first.tick == 1
    assert len(first.storms) == 1
    storm = first.storms[0]
    assert storm.stage == "forming"
    assert storm.currentSystemId == storm.originSystemId
    assert storm.nextSystemId
    assert 0.0 <= storm.pathProgress <= 1.0
    assert len(storm.path) >= 2

    for _ in range(settings.form_ticks):
        sim.step()
    active = sim.snapshot().storms[0]
    assert active.stage == "active"
    origin = active.originSystemId

    # While active the eye should crawl along hyperlanes (progress and/or node change).
    moved = False
    for _ in range(settings.active_ticks * settings.move_interval_ticks + 2):
        snap = sim.step()
        current = snap.storms[0]
        assert current.currentSystemId in current.path
        assert current.nextSystemId in current.path or current.nextSystemId == current.currentSystemId
        assert 0.0 <= current.pathProgress <= 1.0
        center_hops = GalaxyGraphService(tiny_galaxy).systems_within_hops(
            current.currentSystemId if current.pathProgress < 0.5 else current.nextSystemId,
            current.radiusHops,
        )
        for affected in current.affectedSystems:
            assert affected.systemId in center_hops
        if current.currentSystemId != origin or current.pathProgress > 0.05:
            moved = True
            break
    assert moved, "storm eye did not migrate along hyperlanes"

    # Finish lifecycle.
    for _ in range(settings.active_ticks + settings.dissipate_ticks + 2):
        sim.step()
        if not any(item.id == storm.id for item in sim.snapshot().storms):
            break
    assert all(item.id != storm.id for item in sim.snapshot().storms)
    sim.close()


def test_parallel_workers_advance_storms(tiny_galaxy: Path):
    settings = Settings(
        galaxy_index_path=tiny_galaxy,
        seed=11,
        max_active_storms=3,
        spawn_chance=1.0,
        form_ticks=1,
        active_ticks=5,
        dissipate_ticks=1,
        max_radius_hops=1,
        move_interval_ticks=2,
        path_hops_min=2,
        path_hops_max=4,
        worker_processes=2,
        kafka_enabled=False,
        model_enabled=False,
        model_url="",
    )
    sim = StormSimulationService(GalaxyGraphService(tiny_galaxy), settings)
    try:
        for _ in range(5):
            snap = sim.step()
        assert snap.tick == 5
        assert 1 <= len(snap.storms) <= 3
        assert snap.systems
        for storm in snap.storms:
            assert storm.currentSystemId
            assert storm.nextSystemId
            assert storm.path
            assert 0.0 <= storm.pathProgress <= 1.0
    finally:
        sim.close()
