"""Ports: Protocol boundaries between the pure domain and adapters.

Every external system (Ring, AWS, weather, storage, wall clock) sits
behind one of these. Each port gets a live adapter, a cassette for
record/replay, and a fake for unit tests.
"""

from __future__ import annotations

from typing import Protocol

from porch.domain import (
    Detection,
    DeviceState,
    DoorEvent,
    FetchedClip,
    FetchedSnapshot,
    RainRisk,
    Visit,
)


class PortError(Exception):
    """Failure at a port boundary.

    Adapters translate their own failures (SDK errors, missing objects,
    IO problems) into this; nothing else crosses the port boundary.
    """


class EventSource(Protocol):
    """Where door events come from: Playground poll, tape, own footage, webhook."""

    async def poll(self) -> list[DoorEvent]:
        """Fetch new events since the stored cursor."""
        ...


class EventSink(Protocol):
    """Where webhook events go once verified and parsed."""

    async def accept(self, event: DoorEvent) -> None: ...


class MediaFetcher(Protocol):
    """Where event media comes from: tape files for replay, Ring for live."""

    async def snapshots(self, event: DoorEvent) -> list[FetchedSnapshot]:
        """Snapshots inside the event; detections None means annotate."""
        ...

    async def clip(self, event: DoorEvent) -> FetchedClip | None:
        """Clip bytes for the event, None when none is available."""
        ...


class MediaStore(Protocol):
    async def put(self, data: bytes, suffix: str) -> str:
        """Store bytes, return the content key (sha256 + suffix)."""
        ...

    async def get(self, key: str) -> bytes: ...

    async def url(self, key: str, ttl_s: int) -> str:
        """Short-lived pre-signed URL for a stored object."""
        ...


class Labeler(Protocol):
    async def detect(self, image: bytes) -> tuple[Detection, ...]: ...


class LabelReader(Protocol):
    async def read(self, image: bytes) -> tuple[str, ...]:
        """Return text lines found in the image."""
        ...


class ClipDescriber(Protocol):
    async def describe(self, clip_key: str) -> str | None:
        """One-sentence description of the whole clip, None on failure."""
        ...


class Weather(Protocol):
    async def max_rain_probability_pct(self, hours: int) -> RainRisk | None: ...


class Speech(Protocol):
    async def synthesize(self, text: str) -> str:
        """Return the media key of the rendered audio."""
        ...


class Repository(Protocol):
    async def save_visits(self, visits: list[Visit]) -> None: ...

    async def visits_between(self, house_id: str, start_ms: int, end_ms: int) -> list[Visit]:
        """Visits whose start_ms falls in [start_ms, end_ms), ordered by start_ms then id."""
        ...

    async def get_visit(self, visit_id: str) -> Visit | None: ...

    async def claim(self, visit_id: str, resident_id: str) -> Visit | None:
        """Set claimed_by, bump visit and house versions; None when missing."""
        ...

    async def house_version(self, house_id: str) -> int: ...

    async def bump_version(self, house_id: str) -> int: ...

    async def get_cursor(self, device_id: str) -> int | None:
        """Epoch-ms watermark of the last processed event for the device."""
        ...

    async def set_cursor(self, device_id: str, ms: int) -> None: ...

    async def get_device_state(self, device_id: str) -> DeviceState | None:
        """Stitch state + pending events so a stateless worker resumes."""
        ...

    async def set_device_state(self, device_id: str, state: DeviceState) -> None: ...


class Clock(Protocol):
    """Injected wall clock; faked in tests, real elsewhere."""

    def now_ms(self) -> int: ...
