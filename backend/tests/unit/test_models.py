import pytest

from porch.domain import (
    Detection,
    DoorEvent,
    House,
    InvalidCoordinatesError,
    NormBox,
    RainRisk,
    Resident,
    UnknownTimezoneError,
    VisitKind,
    visit_id,
)


def test_normbox_area() -> None:
    box = NormBox(x=0.1, y=0.2, w=0.3, h=0.4)
    assert box.area == pytest.approx(0.12)


@pytest.mark.parametrize(
    ("x", "y", "w", "h"),
    [
        (-0.1, 0.0, 0.5, 0.5),
        (0.0, 1.2, 0.5, 0.5),
        (0.0, 0.0, 0.0, 0.5),
        (0.0, 0.0, 0.5, 0.0),
        (0.0, 0.0, 1.5, 0.5),
        (0.6, 0.0, 0.5, 0.5),  # x + w > 1
        (0.0, 0.7, 0.5, 0.4),  # y + h > 1
    ],
)
def test_normbox_rejects_invalid(x: float, y: float, w: float, h: float) -> None:
    with pytest.raises(ValueError):
        NormBox(x=x, y=y, w=w, h=h)


def test_doorevent_end_before_start_rejected() -> None:
    with pytest.raises(ValueError):
        DoorEvent(
            id="e1",
            device_id="d1",
            kind="motion",
            sub_type="human",
            start_ms=100,
            end_ms=50,
            provenance="ring",
        )


@pytest.mark.parametrize("confidence", [0.0, 0.5, 1.0])
def test_detection_confidence_edges_ok(confidence: float) -> None:
    d = Detection(label="box", confidence=confidence, box=None)
    assert d.confidence == confidence


@pytest.mark.parametrize("confidence", [-0.01, 1.01, 2.0])
def test_detection_confidence_rejected(confidence: float) -> None:
    with pytest.raises(ValueError):
        Detection(label="box", confidence=confidence, box=None)


@pytest.mark.parametrize("pct", [0, 50, 100])
def test_rain_risk_edges_ok(pct: int) -> None:
    assert RainRisk(probability_pct=pct, by_local_time="18:00").probability_pct == pct


@pytest.mark.parametrize("pct", [-1, 101])
def test_rain_risk_rejected(pct: int) -> None:
    with pytest.raises(ValueError):
        RainRisk(probability_pct=pct, by_local_time="18:00")


PRIYA = Resident(id="r1", display_name="Priya Shah")


def test_house_accepts_valid_fields() -> None:
    house = House(
        id="h1",
        timezone="Asia/Tokyo",
        residents=(PRIYA,),
        door_polygon=None,
        latitude=35.6,
        longitude=139.7,
    )
    assert house.residents[0].aliases == ()


def test_house_rejects_unknown_timezone() -> None:
    with pytest.raises(UnknownTimezoneError):
        House(
            id="h1",
            timezone="Not/AZone",
            residents=(),
            door_polygon=None,
            latitude=0.0,
            longitude=0.0,
        )


@pytest.mark.parametrize(("lat", "lon"), [(-91.0, 0.0), (91.0, 0.0), (0.0, -181.0), (0.0, 181.0)])
def test_house_rejects_bad_coordinates(lat: float, lon: float) -> None:
    with pytest.raises(InvalidCoordinatesError):
        House(
            id="h1",
            timezone="UTC",
            residents=(),
            door_polygon=None,
            latitude=lat,
            longitude=lon,
        )


def test_house_rejects_duplicate_resident_ids() -> None:
    twin = Resident(id="r1", display_name="Priya Shahh")
    with pytest.raises(ValueError):
        House(
            id="h1",
            timezone="UTC",
            residents=(PRIYA, twin),
            door_polygon=None,
            latitude=0.0,
            longitude=0.0,
        )


def test_visit_id_deterministic() -> None:
    a = visit_id("dev-1", "evt-1")
    assert a == visit_id("dev-1", "evt-1")
    assert len(a) == 16
    assert all(c in "0123456789abcdef" for c in a)
    assert a != visit_id("dev-1", "evt-2")
    assert a != visit_id("dev-2", "evt-1")


def test_visit_kind_values() -> None:
    assert VisitKind.DELIVERY.value == "delivery"
    assert str(VisitKind.CARS_PASSED) == "cars_passed"
