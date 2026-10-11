"""Enrich one visit: label OCR, door check, rain outlook, clip description.

Every step is gated on the visit kind, timed into a ToolCall, and fails
narrowly (port OSErrors only) so one bad port never drops the visit.
"""

import io
from dataclasses import dataclass, replace

from PIL import Image

from porch.config import Settings
from porch.domain import (
    House,
    NormBox,
    ToolCall,
    Visit,
    VisitKind,
    door_check,
    match_recipient,
)
from porch.ports import (
    ClipDescriber,
    Clock,
    LabelReader,
    MediaStore,
    PortError,
    Weather,
)

_LABEL_KINDS = {VisitKind.DELIVERY, VisitKind.BOX_GONE}


def needs_label(visit: Visit) -> bool:
    """True when a label crop exists to OCR."""
    return visit.kind in _LABEL_KINDS and visit.box is not None and visit.hero_media_key is not None


def needs_door_check(visit: Visit) -> bool:
    """True when the box can be checked against the door zone."""
    return visit.kind == VisitKind.DELIVERY and visit.box is not None


def needs_rain(visit: Visit) -> bool:
    """True when a rain outlook changes the card."""
    return visit.kind == VisitKind.DELIVERY


def needs_clip(visit: Visit) -> bool:
    """True when a clip exists to describe."""
    return visit.clip_media_key is not None


@dataclass(frozen=True, slots=True)
class EnrichPorts:
    media: MediaStore
    reader: LabelReader
    describer: ClipDescriber
    weather: Weather


async def enrich(
    visit: Visit,
    house: House,
    ports: EnrichPorts,
    settings: Settings,
    clock: Clock,
) -> Visit:
    """Run the gated steps in order and return the updated visit."""
    visit = await read_label_step(visit, house, ports, settings, clock)
    visit = check_door_step(visit, house, settings, clock)
    visit = await rain_outlook_step(visit, ports, settings, clock)
    return await describe_clip_step(visit, ports, clock)


def _call(tool: str, ok: bool, start_ms: int, clock: Clock, note: str) -> ToolCall:
    return ToolCall(
        tool=tool,
        ok=ok,
        latency_ms=max(0, clock.monotonic_ms() - start_ms),
        note=note,
    )


def _with_call(visit: Visit, call: ToolCall) -> Visit:
    return replace(visit, trace=(*visit.trace, call))


def _failed(visit: Visit, tool: str, start_ms: int, clock: Clock, exc: PortError) -> Visit:
    note = f"{type(exc).__name__}: {str(exc)[:80]}"
    return _with_call(visit, _call(tool, False, start_ms, clock, note))


async def read_label_step(
    visit: Visit,
    house: House,
    ports: EnrichPorts,
    settings: Settings,
    clock: Clock,
) -> Visit:
    if not needs_label(visit):
        return visit
    assert visit.box is not None and visit.hero_media_key is not None
    start_ms = clock.monotonic_ms()
    try:
        data = await ports.media.get(visit.hero_media_key)
        lines = await ports.reader.read(crop_label(data, visit.box.box, settings))
    except PortError as exc:
        return _failed(visit, "read_label", start_ms, clock, exc)

    match = match_recipient(
        lines,
        house.residents,
        settings.vision.recipient_min_score,
        settings.vision.recipient_margin,
    )
    box = replace(
        visit.box,
        recipient_state=match.state,
        recipient_id=match.resident_id,
    )
    call = _call("read_label", True, start_ms, clock, match.state)
    return _with_call(replace(visit, box=box), call)


def crop_label(data: bytes, box: NormBox, settings: Settings) -> bytes:
    """Box region expanded by label_crop_margin, clamped to the frame."""
    margin = settings.vision.label_crop_margin
    image = Image.open(io.BytesIO(data))
    width, height = image.size
    crop = image.crop(
        (
            int(max(0.0, box.x - margin) * width),
            int(max(0.0, box.y - margin) * height),
            int(min(1.0, box.x + box.w + margin) * width),
            int(min(1.0, box.y + box.h + margin) * height),
        )
    )
    out = io.BytesIO()
    crop.save(out, format="JPEG")
    return out.getvalue()


def check_door_step(
    visit: Visit,
    house: House,
    settings: Settings,
    clock: Clock,
) -> Visit:
    if not needs_door_check(visit):
        return visit
    assert visit.box is not None
    start_ms = clock.monotonic_ms()
    blocks, overlap = door_check(
        visit.box.box, house.door_polygon, settings.vision.door_block_overlap
    )
    call = _call("check_door", True, start_ms, clock, f"blocks={blocks}")
    box = replace(visit.box, blocks_door=blocks, door_overlap=overlap)
    return _with_call(replace(visit, box=box), call)


async def rain_outlook_step(
    visit: Visit,
    ports: EnrichPorts,
    settings: Settings,
    clock: Clock,
) -> Visit:
    if not needs_rain(visit):
        return visit
    start_ms = clock.monotonic_ms()
    try:
        risk = await ports.weather.max_rain_probability_pct(settings.weather.rain_horizon_h)
    except PortError as exc:
        return _failed(visit, "rain_outlook", start_ms, clock, exc)
    if risk is not None and risk.probability_pct < settings.weather.rain_prob_threshold_pct:
        risk = None
    call = _call(
        "rain_outlook",
        True,
        start_ms,
        clock,
        "none" if risk is None else f"{risk.probability_pct}%",
    )
    return _with_call(replace(visit, rain=risk), call)


async def describe_clip_step(
    visit: Visit,
    ports: EnrichPorts,
    clock: Clock,
) -> Visit:
    if not needs_clip(visit):
        return visit
    assert visit.clip_media_key is not None
    start_ms = clock.monotonic_ms()
    try:
        description = await ports.describer.describe(visit.clip_media_key)
    except PortError as exc:
        return _failed(visit, "describe_clip", start_ms, clock, exc)
    call = _call("describe_clip", True, start_ms, clock, "ok" if description else "none")
    if description is not None:
        visit = replace(visit, description=description)
    return _with_call(visit, call)
