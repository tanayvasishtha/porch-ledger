"""JSON codecs for domain values at storage and transport boundaries."""

from pydantic import TypeAdapter

from porch.domain import DeviceState, DoorEvent, Visit

VISIT_ADAPTER: TypeAdapter[Visit] = TypeAdapter(Visit)
DOOR_EVENT_ADAPTER: TypeAdapter[DoorEvent] = TypeAdapter(DoorEvent)
DEVICE_STATE_ADAPTER: TypeAdapter[DeviceState] = TypeAdapter(DeviceState)


def dumps_visit(visit: Visit) -> str:
    """Serialize a Visit to a JSON string."""
    return VISIT_ADAPTER.dump_json(visit).decode()


def loads_visit(payload: str) -> Visit:
    """Parse a JSON string back into a Visit."""
    return VISIT_ADAPTER.validate_json(payload)


def dumps_device_state(state: DeviceState) -> str:
    """Serialize a DeviceState to a JSON string."""
    return DEVICE_STATE_ADAPTER.dump_json(state).decode()


def loads_device_state(payload: str) -> DeviceState:
    """Parse a JSON string back into a DeviceState."""
    return DEVICE_STATE_ADAPTER.validate_json(payload)
