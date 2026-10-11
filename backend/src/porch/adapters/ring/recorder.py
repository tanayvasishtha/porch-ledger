"""Tape recorder: poll a live Ring device and write a replayable tape.

Polls with RingSource on the repository cursor, fetches media with
RingMediaFetcher, and writes a standard tape directory (detections null
means unannotated) with provenance "ring".
"""

from __future__ import annotations

import asyncio
import json
import os
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from pathlib import Path

from porch.adapters.cassette import Cassette
from porch.adapters.ring.client import RingClient
from porch.adapters.ring.playground import RingMediaFetcher, RingSource
from porch.adapters.tape import TAPE_FILE, TAPE_FORMAT
from porch.config import Settings
from porch.domain import DoorEvent, FetchedClip, FetchedSnapshot
from porch.ports import Clock, Repository


@dataclass(frozen=True, slots=True)
class TapeRecorder:
    """The wiring for a recording run; call record() to run it."""

    client: RingClient
    settings: Settings
    device_id: str
    repo: Repository
    cassette: Cassette
    clock: Clock

    async def record(
        self,
        minutes: int,
        out_dir: Path,
        sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
        emit: Callable[[str], None] = print,
    ) -> list[DoorEvent]:
        """Poll until the deadline and write the tape; returns seen events."""
        source = RingSource(self.client, self.device_id, self.repo, self.cassette)
        fetcher = RingMediaFetcher(
            self.client, self.device_id, self.settings, self.cassette, self.clock
        )
        deadline_ms = self.clock.now_ms() + minutes * 60_000
        events: list[DoorEvent] = []
        snapshots: dict[str, list[FetchedSnapshot]] = {}
        clips: dict[str, FetchedClip] = {}
        while self.clock.now_ms() < deadline_ms:
            for event in await source.poll():
                emit(f"{event.id} {event.kind} {event.start_ms}")
                events.append(event)
                snapshots[event.id] = await fetcher.snapshots(event)
                clip = await fetcher.clip(event)
                if clip is not None:
                    clips[event.id] = clip
            await sleep(self.settings.ring.poll_interval_s)
        out_dir.mkdir(parents=True, exist_ok=True)
        _write_tape(out_dir, self.device_id, events, snapshots, clips)
        return events


def _write_tape(
    out_dir: Path,
    device_id: str,
    events: list[DoorEvent],
    snapshots: dict[str, list[FetchedSnapshot]],
    clips: dict[str, FetchedClip],
) -> None:
    snapshot_files = []
    for event in events:
        for snap_index, snap in enumerate(snapshots.get(event.id, [])):
            name = f"{event.id}-{snap_index}{snap.suffix}"
            (out_dir / name).write_bytes(snap.data)
            snapshot_files.append(
                {
                    "event_id": event.id,
                    "at_ms": snap.at_ms,
                    "file": name,
                    "detections": None,
                }
            )
    clip_files = []
    for event in events:
        clip = clips.get(event.id)
        if clip is not None:
            name = f"{event.id}-clip{clip.suffix}"
            (out_dir / name).write_bytes(clip.data)
            clip_files.append({"event_id": event.id, "file": name})
    tape = {
        "format": TAPE_FORMAT,
        "device_id": device_id,
        "provenance": "ring",
        "events": [
            {
                "id": event.id,
                "kind": event.kind,
                "sub_type": event.sub_type,
                "start_ms": event.start_ms,
                "end_ms": event.end_ms,
            }
            for event in events
        ],
        "snapshots": snapshot_files,
        "clips": clip_files,
    }
    (out_dir / TAPE_FILE).write_text(json.dumps(tape, indent=2), encoding="utf-8")


def load_env_value(env_name: str, start_dir: Path) -> str | None:
    """A secret from the environment or the folder's (or parent's) .env."""
    value = os.environ.get(env_name)
    if value:
        return value
    for candidate in (start_dir / ".env", start_dir.parent / ".env"):
        if candidate.is_file():
            found = _parse_env(candidate).get(env_name)
            if found:
                return found
    return None


def _parse_env(path: Path) -> dict[str, str]:
    """Tiny KEY=VALUE reader; no python-dotenv dependency."""
    values: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        key, _, value = stripped.partition("=")
        values[key.strip()] = value.strip().strip('"').strip("'")
    return values
