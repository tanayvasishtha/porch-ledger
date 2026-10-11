"""Ingest service: source events -> stitched visits -> enrichment -> repo.

Media comes through the MediaFetcher port, so tape replay and live Ring
ingest share this path. PorchState and the pending-event buffer live in
memory for the local pipeline; the AWS worker persists them later.
"""

from collections.abc import Sequence
from dataclasses import dataclass, replace

from porch.adapters.tape import TapeSnapshot
from porch.config import Settings, from_settings
from porch.domain import (
    DoorEvent,
    FetchedSnapshot,
    House,
    PorchState,
    Snapshot,
    Visit,
    stitch,
)
from porch.pipeline.agent import PorchClerk
from porch.pipeline.enrich import EnrichPorts, enrich
from porch.pipeline.perception import perceive
from porch.ports import Clock, EventSource, Labeler, MediaFetcher, MediaStore, Repository


@dataclass(frozen=True, slots=True)
class IngestReport:
    events: int
    snapshots: int
    visits_closed: int
    pending: int


@dataclass(frozen=True, slots=True)
class IngestPorts:
    """External systems the service talks to."""

    source: EventSource
    fetcher: MediaFetcher
    media: MediaStore
    labeler: Labeler
    enrich: EnrichPorts
    repo: Repository


@dataclass(frozen=True, slots=True)
class IngestConfig:
    """House context for one ingest run."""

    house: House
    settings: Settings
    clock: Clock


@dataclass(frozen=True, slots=True)
class _EventMedia:
    """Stored media keys for one event, parallel to the fetched order."""

    snapshot_keys: tuple[str, ...]
    clip_key: str | None


class IngestService:
    def __init__(
        self, ports: IngestPorts, config: IngestConfig, clerk: PorchClerk | None = None
    ) -> None:
        self._ports = ports
        self._config = config
        self._clerk = clerk
        self._pending: list[DoorEvent] = []
        self._state = PorchState()

    async def run_once(self) -> IngestReport:
        events = await self._ports.source.poll()
        buffered = [*self._pending, *events]
        if not buffered:
            return IngestReport(events=0, snapshots=0, visits_closed=0, pending=0)
        stored, fetched = await self._store_media(buffered)
        snapshots, snap_count = await self._perceive(buffered, stored, fetched)
        result = stitch(
            buffered,
            snapshots,
            self._state,
            from_settings(self._config.settings.engine),
            self._config.house.id,
            self._config.clock.now_ms(),
        )
        pending_ids = set(result.pending_event_ids)
        self._pending = [e for e in buffered if e.id in pending_ids]
        self._state = result.state
        visits = await self._enrich_all(result.visits, stored)
        await self._ports.repo.save_visits(visits)
        return IngestReport(
            events=len(events),
            snapshots=snap_count,
            visits_closed=len(visits),
            pending=len(self._pending),
        )

    async def _store_media(
        self, events: Sequence[DoorEvent]
    ) -> tuple[dict[str, _EventMedia], dict[str, list[FetchedSnapshot]]]:
        """Fetch media for each event and store bytes in the MediaStore."""
        stored: dict[str, _EventMedia] = {}
        fetched: dict[str, list[FetchedSnapshot]] = {}
        for event in events:
            snapshots = await self._ports.fetcher.snapshots(event)
            fetched[event.id] = snapshots
            keys = tuple(
                [await self._ports.media.put(snap.data, snap.suffix) for snap in snapshots]
            )
            clip = await self._ports.fetcher.clip(event)
            clip_key = await self._ports.media.put(clip.data, clip.suffix) if clip else None
            stored[event.id] = _EventMedia(snapshot_keys=keys, clip_key=clip_key)
        return stored, fetched

    async def _perceive(
        self,
        buffered: list[DoorEvent],
        stored: dict[str, _EventMedia],
        fetched: dict[str, list[FetchedSnapshot]],
    ) -> tuple[dict[str, Sequence[Snapshot]], int]:
        snapshots: dict[str, Sequence[Snapshot]] = {}
        count = 0
        for event in buffered:
            tape_snaps = [
                TapeSnapshot(
                    event_id=event.id,
                    at_ms=snap.at_ms,
                    file=stored[event.id].snapshot_keys[index],
                    detections=snap.detections,
                )
                for index, snap in enumerate(fetched[event.id])
            ]
            snapshots[event.id] = await perceive(
                tape_snaps, self._ports.labeler, self._ports.media, self._config.settings
            )
            count += len(tape_snaps)
        return snapshots, count

    def _clip_key(self, visit: Visit, stored: dict[str, _EventMedia]) -> str | None:
        for event_id in reversed(visit.event_ids):
            clip_key = stored.get(event_id, _EventMedia((), None)).clip_key
            if clip_key is not None:
                return clip_key
        return None

    async def _enrich_all(
        self, visits: tuple[Visit, ...], stored: dict[str, _EventMedia]
    ) -> list[Visit]:
        out = []
        for visit in visits:
            with_clip = replace(visit, clip_media_key=self._clip_key(visit, stored))
            if self._clerk is not None:
                out.append(await self._clerk.enrich(with_clip))
            else:
                out.append(
                    await enrich(
                        with_clip,
                        self._config.house,
                        self._ports.enrich,
                        self._config.settings,
                        self._config.clock,
                    )
                )
        return out
