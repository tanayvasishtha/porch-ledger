"""Shared fakes and factories for adapter and API tests."""

from dataclasses import replace
from pathlib import Path

from porch.domain import House, Resident, Visit, VisitKind

REPO_ROOT = Path(__file__).resolve().parents[2]
DEMO_FIXTURE = REPO_ROOT / "fixtures" / "house.demo.json"


def demo_house() -> House:
    return House(
        id="demo",
        timezone="America/Los_Angeles",
        residents=(
            Resident(id="priya", display_name="Priya Shah", aliases=("P Shah",)),
            Resident(id="sam", display_name="Sam Okafor"),
            Resident(id="jo", display_name="Jo Lindqvist"),
        ),
        door_polygon=None,
        latitude=47.6205,
        longitude=-122.3493,
    )


def mkvisit(
    vid: str,
    start_ms: int,
    kind: VisitKind = VisitKind.ACTIVITY,
    house_id: str = "demo",
) -> Visit:
    return Visit(
        id=vid,
        house_id=house_id,
        device_id="d1",
        kind=kind,
        start_ms=start_ms,
        end_ms=start_ms + 1000,
        event_ids=("e1",),
        hero_media_key=None,
        clip_media_key=None,
        box=None,
        description=None,
        rain=None,
        provenance="replay",
        trace=(),
        claimed_by=None,
        version=1,
    )


class FakeRepo:
    """In-memory Repository for API tests."""

    def __init__(self, visits: list[Visit] | None = None) -> None:
        self._visits = {v.id: v for v in (visits or [])}
        self._versions: dict[str, int] = {}
        self._cursors: dict[str, int] = {}

    async def save_visits(self, visits: list[Visit]) -> None:
        changed = False
        for visit in visits:
            if self._visits.get(visit.id) != visit:
                self._visits[visit.id] = visit
                changed = True
        if changed:
            houses = {v.house_id for v in visits}
            for house_id in houses:
                await self.bump_version(house_id)

    async def visits_between(self, house_id: str, start_ms: int, end_ms: int) -> list[Visit]:
        found = [
            v
            for v in self._visits.values()
            if v.house_id == house_id and start_ms <= v.start_ms < end_ms
        ]
        return sorted(found, key=lambda v: (v.start_ms, v.id))

    async def get_visit(self, visit_id: str) -> Visit | None:
        return self._visits.get(visit_id)

    async def claim(self, visit_id: str, resident_id: str) -> Visit | None:
        visit = self._visits.get(visit_id)
        if visit is None:
            return None
        updated = replace(visit, claimed_by=resident_id, version=visit.version + 1)
        self._visits[visit_id] = updated
        await self.bump_version(visit.house_id)
        return updated

    async def house_version(self, house_id: str) -> int:
        return self._versions.get(house_id, 0)

    async def bump_version(self, house_id: str) -> int:
        self._versions[house_id] = self._versions.get(house_id, 0) + 1
        return self._versions[house_id]

    async def get_cursor(self, device_id: str) -> int | None:
        return self._cursors.get(device_id)

    async def set_cursor(self, device_id: str, ms: int) -> None:
        self._cursors[device_id] = ms


class FakeClock:
    def __init__(self, now_ms: int) -> None:
        self._now_ms = now_ms

    def now_ms(self) -> int:
        return self._now_ms
