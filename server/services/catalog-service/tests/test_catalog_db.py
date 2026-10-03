from __future__ import annotations

from app.service.catalog_query_service import CatalogQueryService


def test_catalog_serves_seeded_systems_from_db():
    catalog = CatalogQueryService()
    health = catalog.health()
    assert health["hasSystems"] is True

    index = catalog.get_galaxy_index()
    assert index["meta"].get("source") == "EfolsMiradinsPact"
    assert len(index["systems"]) >= 3000

    graph = catalog.get_galaxy_graph()
    assert len(graph["systems"]) == len(index["systems"])
    assert set(graph["systems"][0]) == {"id", "kind"}
    assert len(graph["edgesDisplay"]) == len(index["edgesDisplay"])
    assert len(graph["edgesCanon"]) == len(index["edgesCanon"])

    sample = next(system for system in index["systems"] if system["token"] == "MiradinSirius")
    detail = catalog.get_system_by_id(sample["id"])
    assert detail["id"] == sample["id"]
    assert isinstance(detail.get("worlds"), list)
