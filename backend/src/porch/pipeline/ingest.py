"""Ingest service: tape events -> stitched visits -> enrichment -> repo.

PorchState and the pending-event buffer live in memory for the local
pipeline; the AWS worker persists them in a later commit.
"""

from collections.abc import Sequence
from dataclasses import dataclass, replace
from pathlib import Path

from porch.adapters.tape import TapeClip, TapeSnapshot, load_tape
from porch.config import Settings, from_settings
from porch.domain import DoorEvent, House, PorchState, Snapshot, Visit, stitch
from porch.pipeline.enrich import EnrichPorts, enrich
from porch.pipeline.perception import perceive
from porch.ports import Clock, EventSource, Labeler, MediaStore, Repository


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
    media: MediaStore
    labeler: Labeler
    enrich: EnrichPorts
    repo: Repository


@dataclass(frozen=True, slots=True)
class IngestConfig:
    """House context plus where to find the tape, if there is one."""

    house: House
    settings: Settings
    clock: Clock
    tape_dir: Path | None = None


class IngestService:
    def __init__(self, ports: IngestPorts, config: IngestConfig) -> None:
        self._ports = ports
        self._config = config
        self._tape = load_tape(config.tape_dir) if config.tape_dir else None
        self._pending: list[DoorEvent] = []
        self._state = PorchState()

    async def run_once(self) -> IngestReport:
        events = await self._ports.source.poll()
        buffered = [*self._pending, *events]
        if not buffered:
            return IngestReport(events=0, snapshots=0, visits_closed=0, pending=0)
        stored = await self._store_media(buffered)
        snapshots, snap_count = await self._perceive(buffered, stored)
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

    def _snaps(self, event_id: str) -> tuple[TapeSnapshot, ...]:
        return self._tape.snapshots_for(event_id) if self._tape else ()

    def _clip(self, event_id: str) -> TapeClip | None:
        return self._tape.clip_for(event_id) if self._tape else None

    async def _put_file(self, name: str) -> str:
        # Unreachable without a tape: _snaps/_clip yield nothing then.
        assert self._tape is not None
        data = (self._tape.path / name).read_bytes()
        return await self._ports.media.put(data, Path(name).suffix)

    async def _store_media(self, events: Sequence[DoorEvent]) -> dict[str, str]:
        stored: dict[str, str] = {}
        for event in events:
            for snap in self._snaps(event.id):
                if snap.file not in stored:
                    stored[snap.file] = await self._put_file(snap.file)
            clip = self._clip(event.id)
            if clip is not None and clip.file not in stored:
                stored[clip.file] = await self._put_file(clip.file)
        return stored

    async def _perceive(
        self, buffered: list[DoorEvent], stored: dict[str, str]
    ) -> tuple[dict[str, Sequence[Snapshot]], int]:
        snapshots: dict[str, Sequence[Snapshot]] = {}
        count = 0
        for event in buffered:
            tape_snaps = [replace(s, file=stored[s.file]) for s in self._snaps(event.id)]
            snapshots[event.id] = await perceive(
                tape_snaps, self._ports.labeler, self._ports.media, self._config.settings
            )
            count += len(tape_snaps)
        return snapshots, count

    def _clip_key(self, visit: Visit, stored: dict[str, str]) -> str | None:
        for event_id in reversed(visit.event_ids):
            clip = self._clip(event_id)
            if clip is not None:
                return stored[clip.file]
        return None

    async def _enrich_all(self, visits: tuple[Visit, ...], stored: dict[str, str]) -> list[Visit]:
        out = []
        for visit in visits:
            with_clip = replace(visit, clip_media_key=self._clip_key(visit, stored))
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
