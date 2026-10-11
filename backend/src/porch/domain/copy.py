"""Deterministic wording for visit cards shown on TV and tablets.

All phrasing is fixed here: same input always produces the same strings.
Times are rendered in the house timezone, 12-hour clock, lowercase am/pm.
"""

from dataclasses import dataclass
from datetime import datetime
from zoneinfo import ZoneInfo

from porch.domain.models import BoxFacts, House, Visit, VisitKind

MS_PER_MINUTE = 60_000
NOON_HOUR = 12
MIN_STOPPED_MINUTES = 1

_TITLES = {
    VisitKind.DELIVERY: "Delivery",
    VisitKind.BOX_GONE: "Box gone",
    VisitKind.CAR_STOPPED: "Car stopped",
    VisitKind.VISITOR: "Visitor",
    VisitKind.CARS_PASSED: "Car passed",
    VisitKind.ACTIVITY: "Movement",
}

_DESCRIPTIONS = {
    VisitKind.DELIVERY: "A box was left at the door.",
    VisitKind.BOX_GONE: "A box that was at the door is gone.",
    VisitKind.VISITOR: "Someone came to the door.",
    VisitKind.CARS_PASSED: "A car drove past.",
    VisitKind.ACTIVITY: "Movement near the door.",
}


@dataclass(frozen=True, slots=True)
class CardText:
    title: str
    span: str
    facts: tuple[str, ...]
    description: str


def card_text(visit: Visit, house: House) -> CardText:
    """Fixed wording for one visit card."""
    stopped_min = _stopped_minutes(visit)
    description = visit.description or _description(visit, stopped_min)
    return CardText(
        title=_TITLES[visit.kind],
        span=_span(visit, house),
        facts=tuple(_facts(visit, house, stopped_min)),
        description=description,
    )


def _local(ms: int, tz: ZoneInfo) -> datetime:
    return datetime.fromtimestamp(ms / 1000, tz=tz)


def _short(dt: datetime) -> str:
    hour = dt.hour % NOON_HOUR or NOON_HOUR
    return f"{hour}:{dt.minute:02d}"


def _period(dt: datetime) -> str:
    return "am" if dt.hour < NOON_HOUR else "pm"


def _clock(dt: datetime) -> str:
    return f"{_short(dt)} {_period(dt)}"


def _span(visit: Visit, house: House) -> str:
    tz = ZoneInfo(house.timezone)
    start = _local(visit.start_ms, tz)
    end = _local(visit.end_ms, tz)
    if (start.hour, start.minute) == (end.hour, end.minute):
        return _clock(start)
    if _period(start) == _period(end):
        return f"{_short(start)} to {_clock(end)}"
    return f"{_clock(start)} to {_clock(end)}"


def _stopped_minutes(visit: Visit) -> int:
    if visit.kind != VisitKind.CAR_STOPPED:
        return 0
    return max(MIN_STOPPED_MINUTES, round((visit.end_ms - visit.start_ms) / MS_PER_MINUTE))


def _facts(visit: Visit, house: House, stopped_min: int) -> list[str]:
    facts: list[str] = []
    if (box := visit.box) is not None:
        facts.extend(_recipient_fact(box, house))
        if box.blocks_door is True:
            facts.append("Leaning on the door")
    if stopped_min:
        facts.append(f"Stopped {stopped_min} min")
    if visit.rain is not None:
        facts.append(f"Rain likely by {visit.rain.by_local_time}")
    return facts


def _recipient_fact(box: BoxFacts, house: House) -> list[str]:
    if box.recipient_state == "matched":
        resident = next((r for r in house.residents if r.id == box.recipient_id), None)
        return [f"Box for {resident.display_name}"] if resident is not None else []
    if box.recipient_state == "unreadable":
        return ["Label not readable"]
    if box.recipient_state == "not_ours":
        return ["Not for anyone here"]
    return []


def _description(visit: Visit, stopped_min: int) -> str:
    if visit.kind == VisitKind.CAR_STOPPED:
        return f"A car stopped outside for {stopped_min} min."
    return _DESCRIPTIONS[visit.kind]
