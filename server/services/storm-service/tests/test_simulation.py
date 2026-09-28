from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.config.settings import Settings
from app.service.galaxy_graph_service import GalaxyGraphService
from app.service.storm_simulation_service import StormSimulationService


@pytest.fixture()
def tiny_galaxy(tmp_path: Path) -> Path:
    payload = {
        "systems": [
            {"id": "A:One", "kind": "star", "x": 0.0, "y": 0.0, "z": 0.0},
            {"id": "A:Two", "kind": "star", "x": 0.1, "y": 0.0, "z": 0.0},
            {"id": "A:Three", "kind": "star", "x": 0.2, "y": 0.0, "z": 0.0},
            {"id": "A:Isle", "kind": "star", "x": 0.9, "y": 0.9, "z": 0.0},
        ],
        "edgesDisplay": [
            {"a": "A:One", "b": "A:Two"},
            {"a": "A:Two", "b": "A:Three"},
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


def test_storm_lifecycle_and_spawn(tiny_galaxy: Path):
    settings = Settings(
        galaxy_index_path=tiny_galaxy,
        seed=7,
        tick_seconds=1,
        max_active_storms=2,
        spawn_chance=1.0,
        form_ticks=2,
        active_ticks=4,
        dissipate_ticks=2,
        max_radius_hops=2,
    )
    sim = StormSimulationService(GalaxyGraphService(tiny_galaxy), settings)

    first = sim.step()
    assert first.tick == 1
    assert len(first.storms) == 1
    storm = first.storms[0]
    assert storm.stage == "forming"
    assert storm.originSystemId in {"A:One", "A:Two", "A:Three", "A:Isle"}

    for _ in range(2):
        sim.step()
    active = sim.snapshot().storms[0]
    assert active.stage == "active"
    assert active.radiusHops >= 1
    hops = GalaxyGraphService(tiny_galaxy).systems_within_hops(active.originSystemId, active.radiusHops)
    for affected in active.affectedSystems:
        assert affected.systemId in hops
        assert affected.hopsFromOrigin == hops[affected.systemId]

    for _ in range(settings.active_ticks):
        sim.step()
    dissipating = [item for item in sim.snapshot().storms if item.id == active.id]
    assert dissipating
    assert dissipating[0].stage == "dissipating"

    for _ in range(settings.dissipate_ticks + 1):
        sim.step()
    assert all(item.id != active.id for item in sim.snapshot().storms)
