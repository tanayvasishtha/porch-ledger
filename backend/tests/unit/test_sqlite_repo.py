import asyncio
from dataclasses import replace
from pathlib import Path

from porch.adapters.local import SqliteRepository
from porch.domain import Visit, VisitKind


def mkvisit(vid: str, start_ms: int, house_id: str = "h1") -> Visit:
    return Visit(
        id=vid,
        house_id=house_id,
        device_id="d1",
        kind=VisitKind.ACTIVITY,
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


def test_save_get_and_missing(tmp_path: Path) -> None:
    async def run() -> None:
        repo = SqliteRepository(tmp_path / "repo.db")
        visit = mkvisit("v1", 1000)
        await repo.save_visits([visit])
        assert await repo.get_visit("v1") == visit
        assert await repo.get_visit("missing") is None

    asyncio.run(run())


def test_visits_between_bounds_and_order(tmp_path: Path) -> None:
    async def run() -> None:
        repo = SqliteRepository(tmp_path / "repo.db")
        v1 = mkvisit("v1", 3000)
        v2 = mkvisit("v2", 1000)
        v3 = mkvisit("v3", 2000)
        other = mkvisit("v4", 1500, house_id="h2")
        await repo.save_visits([v1, v2, v3, other])
        window = await repo.visits_between("h1", 1500, 3000)
        assert [v.id for v in window] == ["v3"]
        everything = await repo.visits_between("h1", 0, 4000)
        assert [v.id for v in everything] == ["v2", "v3", "v1"]

    asyncio.run(run())


def test_upsert_preserves_claim_and_version(tmp_path: Path) -> None:
    async def run() -> None:
        repo = SqliteRepository(tmp_path / "repo.db")
        original = mkvisit("v1", 1000)
        await repo.save_visits([original])
        claimed = await repo.claim("v1", "r1")
        assert claimed is not None
        assert claimed.claimed_by == "r1"
        assert claimed.version == 2
        house_version = await repo.house_version("h1")
        await repo.save_visits([original])
        stored = await repo.get_visit("v1")
        assert stored is not None
        assert stored.claimed_by == "r1"
        assert stored.version == 2
        assert await repo.house_version("h1") == house_version

    asyncio.run(run())


def test_upsert_changed_visit_increments_version(tmp_path: Path) -> None:
    async def run() -> None:
        repo = SqliteRepository(tmp_path / "repo.db")
        original = mkvisit("v1", 1000)
        await repo.save_visits([original])
        claimed = await repo.claim("v1", "r1")
        assert claimed is not None
        house_version = await repo.house_version("h1")
        changed = replace(original, description="New description")
        await repo.save_visits([changed])
        stored = await repo.get_visit("v1")
        assert stored is not None
        assert stored.claimed_by == "r1"
        assert stored.version == 3
        assert stored.description == "New description"
        assert await repo.house_version("h1") == house_version + 1

    asyncio.run(run())


def test_claim_and_version_bumps(tmp_path: Path) -> None:
    async def run() -> None:
        repo = SqliteRepository(tmp_path / "repo.db")
        assert await repo.house_version("h1") == 0
        await repo.save_visits([mkvisit("v1", 1000)])
        assert await repo.house_version("h1") == 1
        claimed = await repo.claim("v1", "r1")
        assert claimed is not None and claimed.version == 2
        assert await repo.house_version("h1") == 2
        assert await repo.claim("missing", "r1") is None
        assert await repo.house_version("h1") == 2

    asyncio.run(run())


def test_identical_save_does_not_bump(tmp_path: Path) -> None:
    async def run() -> None:
        repo = SqliteRepository(tmp_path / "repo.db")
        visit = mkvisit("v1", 1000)
        await repo.save_visits([visit])
        assert await repo.house_version("h1") == 1
        await repo.save_visits([visit])
        assert await repo.house_version("h1") == 1

    asyncio.run(run())


def test_cursor_roundtrip(tmp_path: Path) -> None:
    async def run() -> None:
        repo = SqliteRepository(tmp_path / "repo.db")
        assert await repo.get_cursor("d1") is None
        await repo.set_cursor("d1", 500)
        assert await repo.get_cursor("d1") == 500
        await repo.set_cursor("d1", 700)
        assert await repo.get_cursor("d1") == 700

    asyncio.run(run())


def test_bump_version(tmp_path: Path) -> None:
    async def run() -> None:
        repo = SqliteRepository(tmp_path / "repo.db")
        assert await repo.bump_version("h1") == 1
        assert await repo.bump_version("h1") == 2

    asyncio.run(run())
