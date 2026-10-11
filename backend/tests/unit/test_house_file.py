from pathlib import Path

import pytest
from pydantic import ValidationError

from porch.adapters.local.house_file import load_house
from porch.domain import UnknownTimezoneError
from tests.helpers import DEMO_FIXTURE


def test_loads_demo_fixture() -> None:
    house = load_house(DEMO_FIXTURE)
    assert house.id == "demo"
    assert house.timezone == "America/Los_Angeles"
    assert len(house.residents) == 3
    assert house.residents[0].aliases == ("P Shah",)
    assert house.door_polygon is not None
    assert len(house.door_polygon) == 4


def test_rejects_wrong_shape(tmp_path: Path) -> None:
    bad = tmp_path / "house.json"
    bad.write_text('{"id": "h", "timezone": "UTC", "latitude": "nope"}', encoding="utf-8")
    with pytest.raises(ValidationError):
        load_house(bad)


def test_rejects_bad_timezone(tmp_path: Path) -> None:
    bad = tmp_path / "house.json"
    bad.write_text(
        '{"id": "h", "timezone": "Nowhere/Zone", "residents": [],'
        ' "door_polygon": null, "latitude": 0.0, "longitude": 0.0}',
        encoding="utf-8",
    )
    with pytest.raises(UnknownTimezoneError):
        load_house(bad)
