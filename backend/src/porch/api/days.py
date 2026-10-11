"""Local-day helpers: 'today' and day bounds in the house timezone."""

from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

from porch.domain import House
from porch.ports import Clock

MS_PER_S = 1000

_WEEKDAYS = ("Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday")
_MONTHS = (
    "January",
    "February",
    "March",
    "April",
    "May",
    "June",
    "July",
    "August",
    "September",
    "October",
    "November",
    "December",
)


def day_bounds(day: date, house: House) -> tuple[int, int]:
    """Epoch-ms half-open range for one local day, DST-safe via zoneinfo."""
    tz = ZoneInfo(house.timezone)
    start = datetime.combine(day, time.min, tzinfo=tz)
    end = start + timedelta(days=1)
    return int(start.timestamp() * MS_PER_S), int(end.timestamp() * MS_PER_S)


def today(house: House, clock: Clock) -> date:
    """Current local date for the house."""
    tz = ZoneInfo(house.timezone)
    return datetime.fromtimestamp(clock.now_ms() / MS_PER_S, tz=tz).date()


def day_label(house: House, clock: Clock) -> str:
    """ "Monday, June 1" for today in the house timezone; no locale needed."""
    day = today(house, clock)
    return f"{_WEEKDAYS[day.weekday()]}, {_MONTHS[day.month - 1]} {day.day}"
