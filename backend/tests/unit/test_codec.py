from porch.adapters.codec import DOOR_EVENT_ADAPTER, dumps_visit, loads_visit
from porch.domain import (
    BoxFacts,
    DoorEvent,
    NormBox,
    RainRisk,
    ToolCall,
    Visit,
    VisitKind,
)


def test_visit_roundtrip_with_nested_fields() -> None:
    visit = Visit(
        id="v1",
        house_id="h1",
        device_id="dev-1",
        kind=VisitKind.DELIVERY,
        start_ms=1000,
        end_ms=2000,
        event_ids=("e1", "e2"),
        hero_media_key="snap-1",
        clip_media_key=None,
        box=BoxFacts(
            box=NormBox(x=0.1, y=0.1, w=0.2, h=0.2),
            recipient_id="r1",
            recipient_state="matched",
            blocks_door=True,
            door_overlap=0.42,
        ),
        description="A courier dropped a box.",
        rain=RainRisk(probability_pct=80, by_local_time="6:30 pm"),
        provenance="replay",
        trace=(ToolCall(tool="rekognition", ok=True, latency_ms=120, note="labels"),),
        claimed_by=None,
        version=3,
    )
    assert loads_visit(dumps_visit(visit)) == visit


def test_visit_roundtrip_sparse() -> None:
    visit = Visit(
        id="v2",
        house_id="h1",
        device_id="dev-1",
        kind=VisitKind.ACTIVITY,
        start_ms=5,
        end_ms=6,
        event_ids=(),
        hero_media_key=None,
        clip_media_key=None,
        box=None,
        description=None,
        rain=None,
        provenance="ring",
        trace=(),
        claimed_by="r2",
        version=1,
    )
    assert loads_visit(dumps_visit(visit)) == visit


def test_door_event_adapter() -> None:
    event = DoorEvent(
        id="e1",
        device_id="d1",
        kind="ding",
        sub_type=None,
        start_ms=5,
        end_ms=6,
        provenance="ring",
    )
    payload = DOOR_EVENT_ADAPTER.dump_json(event)
    assert DOOR_EVENT_ADAPTER.validate_json(payload) == event
