"""JSON codecs for domain values at storage and transport boundaries."""

from pydantic import TypeAdapter

from porch.domain import DoorEvent, Visit

VISIT_ADAPTER: TypeAdapter[Visit] = TypeAdapter(Visit)
DOOR_EVENT_ADAPTER: TypeAdapter[DoorEvent] = TypeAdapter(DoorEvent)


def dumps_visit(visit: Visit) -> str:
    """Serialize a Visit to a JSON string."""
    return VISIT_ADAPTER.dump_json(visit).decode()


def loads_visit(payload: str) -> Visit:
    """Parse a JSON string back into a Visit."""
    return VISIT_ADAPTER.validate_json(payload)
