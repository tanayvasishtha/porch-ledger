"""Ring polling source and media fetcher for the live pipeline.

RingSource polls Event History for one device and keeps the repository
cursor at the max end_ms seen. RingMediaFetcher turns events into
snapshots (fixed offsets into the event, clamped to now) and one clip.
Both go through the Cassette so a recorded session replays offline.
"""

import asyncio

from pydantic import TypeAdapter

from porch.adapters.cassette import Cassette, CassetteMissError, JsonValue
from porch.adapters.ring.client import RingClient, RingEvent
from porch.config import Settings
from porch.domain import DoorEvent, EventKind, FetchedClip, FetchedSnapshot
from porch.ports import Clock, EventSource, MediaFetcher, Repository

_EVENTS = TypeAdapter(list[RingEvent])

_KINDS: dict[str, EventKind] = {
    "motion": "motion",
    "ding": "ding",
    "on_demand": "on_demand",
}


class _NoMediaError(Exception):
    """The service returned no media; the cassette records nothing."""


class RingSource(EventSource):
    def __init__(
        self, client: RingClient, device_id: str, repo: Repository, cassette: Cassette
    ) -> None:
        self._client = client
        self._device_id = device_id
        self._repo = repo
        self._cassette = cassette

    async def poll(self) -> list[DoorEvent]:
        since_ms = await self._repo.get_cursor(self._device_id) or 0
        request: dict[str, JsonValue] = {
            "device_id": self._device_id,
            "since_ms": since_ms,
        }
        events = await self._cassette.call(
            "ring", 1, request, lambda: self._client.history(self._device_id, since_ms), _EVENTS
        )
        door_events = [event for raw in events if (event := _door_event(raw)) is not None]
        if events:
            await self._repo.set_cursor(self._device_id, max(e.end_ms for e in events))
        return door_events


class RingMediaFetcher(MediaFetcher):
    def __init__(
        self,
        client: RingClient,
        device_id: str,
        settings: Settings,
        cassette: Cassette,
        clock: Clock,
    ) -> None:
        self._client = client
        self._device_id = device_id
        self._offsets = settings.ring.snapshot_offsets
        self._cassette = cassette
        self._clock = clock

    async def snapshots(self, event: DoorEvent) -> list[FetchedSnapshot]:
        duration = max(event.end_ms - event.start_ms, 0)
        now_ms = self._clock.now_ms()
        offsets = [min(event.start_ms + int(duration * offset), now_ms) for offset in self._offsets]
        fetched = await asyncio.gather(*(self._snapshot_at(at_ms) for at_ms in offsets))
        return [snap for snap in fetched if snap is not None]

    async def clip(self, event: DoorEvent) -> FetchedClip | None:
        duration_ms = max(event.end_ms - event.start_ms, 0)
        request: dict[str, JsonValue] = {
            "device_id": self._device_id,
            "start_ms": event.start_ms,
            "duration_ms": duration_ms,
        }
        try:
            data = await self._cassette.call_bytes(
                "ring_clip", 1, request, lambda: self._clip_bytes(event.start_ms, duration_ms)
            )
        except (_NoMediaError, CassetteMissError):
            return None
        return FetchedClip(data=data, suffix=".mp4")

    async def _snapshot_at(self, at_ms: int) -> FetchedSnapshot | None:
        request: dict[str, JsonValue] = {"device_id": self._device_id, "at_ms": at_ms}
        try:
            data = await self._cassette.call_bytes(
                "ring_snap", 1, request, lambda: self._snapshot_bytes(at_ms)
            )
        except (_NoMediaError, CassetteMissError):
            return None
        return FetchedSnapshot(at_ms=at_ms, data=data, suffix=".jpg", detections=None)

    async def _snapshot_bytes(self, at_ms: int) -> bytes:
        data = await self._client.snapshot(self._device_id, at_ms)
        if data is None:
            raise _NoMediaError
        return data

    async def _clip_bytes(self, start_ms: int, duration_ms: int) -> bytes:
        data = await self._client.clip(self._device_id, start_ms, duration_ms)
        if data is None:
            raise _NoMediaError
        return data


def _door_event(raw: RingEvent) -> DoorEvent | None:
    kind = _KINDS.get(raw.event_type)
    if kind is None:
        return None
    return DoorEvent(
        id=raw.id,
        device_id=raw.device_id,
        kind=kind,
        sub_type=raw.sub_type,
        start_ms=raw.start_ms,
        end_ms=raw.end_ms,
        provenance="ring",
    )
