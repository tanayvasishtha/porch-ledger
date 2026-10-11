"""Turn tape snapshots into domain Snapshots.

Annotated tape snapshots (detections is a list, even empty) are used
as-is. Unannotated ones read bytes from media and call the Labeler,
bounded by a semaphore sized from rekognition_concurrency.
"""

import asyncio
from collections.abc import Sequence

from porch.adapters.tape import TapeSnapshot
from porch.config import Settings
from porch.domain import Snapshot
from porch.ports import Labeler, MediaStore


async def perceive(
    snapshots: Sequence[TapeSnapshot],
    labeler: Labeler,
    media: MediaStore,
    settings: Settings,
) -> tuple[Snapshot, ...]:
    """Domain Snapshots for one event, in tape order."""
    semaphore = asyncio.Semaphore(settings.aws.rekognition_concurrency)
    results = await asyncio.gather(
        *(_perceive_one(s, semaphore, labeler, media) for s in snapshots)
    )
    return tuple(results)


async def _perceive_one(
    snap: TapeSnapshot,
    semaphore: asyncio.Semaphore,
    labeler: Labeler,
    media: MediaStore,
) -> Snapshot:
    if snap.detections is not None:
        return Snapshot(
            event_id=snap.event_id,
            at_ms=snap.at_ms,
            media_key=snap.file,
            detections=snap.detections,
        )
    data = await media.get(snap.file)
    async with semaphore:
        detections = await labeler.detect(data)
    return Snapshot(
        event_id=snap.event_id,
        at_ms=snap.at_ms,
        media_key=snap.file,
        detections=tuple(detections),
    )
