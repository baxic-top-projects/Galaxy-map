from __future__ import annotations

from app.db.models import SystemRow


def test_system_row_mapping():
    row = SystemRow(
        id="Miradin_Empire:MiradinSirius",
        token="MiradinSirius",
        stem="Miradin_Empire",
        kind="star",
        name_en="Miradin Sirius",
        name_ru="Мирадинский Сириус",
        star_type_key="binary_class_g",
        sector_id="SEC",
        capital=True,
        x=0.1,
        y=0.2,
        z=0.3,
        world_count=1,
        shard="systems/Miradin_Empire__MiradinSirius.json",
        detail={"id": "Miradin_Empire:MiradinSirius", "worlds": []},
    )
    assert row.id.startswith("Miradin_Empire:")
    assert row.detail["worlds"] == []
