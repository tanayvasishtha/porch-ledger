"""Repository contract: every backend must pass the same suite.

Parametrized over SqliteRepository and DynamoRepository (with the
in-memory FakeDynamoClient that enforces condition expressions).
"""

import asyncio
from collections.abc import Iterator
from dataclasses import replace
from pathlib import Path
from typing import cast

import pytest
from types_boto3_dynamodb.client import DynamoDBClient

from porch.adapters.aws.dynamo_repo import DynamoRepository
from porch.adapters.local import SqliteRepository
from porch.domain import DeviceState, PorchState, VisitKind
from porch.ports import Repository
from tests.helpers import FakeDynamoClient, mkvisit


@pytest.fixture(params=["sqlite", "dynamo"])
def repo(tmp_path: Path, request: pytest.FixtureRequest) -> Iterator[Repository]:
    if request.param == "sqlite":
        yield SqliteRepository(tmp_path / "repo.db")
    else:
        yield DynamoRepository(cast("DynamoDBClient", FakeDynamoClient()), "porch")


def test_save_get_and_missing(repo: Repository) -> None:
    async def run() -> None:
        visit = mkvisit("v1", 1000, house_id="h1")
        await repo.save_visits([visit])
        assert await repo.get_visit("v1") == visit
        assert await repo.get_visit("missing") is None

    asyncio.run(run())


def test_visits_between_bounds_and_order(repo: Repository) -> None:
    async def run() -> None:
        v1 = mkvisit("v1", 3000, house_id="h1")
        v2 = mkvisit("v2", 1000, house_id="h1")
        v3 = mkvisit("v3", 2000, house_id="h1")
        other = mkvisit("v4", 1500, house_id="h2")
        await repo.save_visits([v1, v2, v3, other])
        window = await repo.visits_between("h1", 1500, 3000)
        assert [v.id for v in window] == ["v3"]
        everything = await repo.visits_between("h1", 0, 4000)
        assert [v.id for v in everything] == ["v2", "v3", "v1"]

    asyncio.run(run())


def test_upsert_preserves_claim_and_version(repo: Repository) -> None:
    async def run() -> None:
        original = mkvisit("v1", 1000, house_id="h1")
        await repo.save_visits([original])
        claimed = await repo.claim("v1", "priya")
        assert claimed is not None and claimed.claimed_by == "priya"
        older = replace(original, description="stale overwrite")
        await repo.save_visits([older])
        stored = await repo.get_visit("v1")
        assert stored is not None
        assert stored.claimed_by == "priya"
        assert stored.description == "stale overwrite"
        assert stored.version == claimed.version + 1

    asyncio.run(run())


def test_claim_missing_and_repeat(repo: Repository) -> None:
    async def run() -> None:
        assert await repo.claim("nope", "priya") is None
        visit = mkvisit("v1", 1000, house_id="h1")
        await repo.save_visits([visit])
        first = await repo.claim("v1", "priya")
        second = await repo.claim("v1", "sam")
        assert first is not None and second is not None
        assert second.claimed_by == "sam"
        assert second.version == (first.version if first else 0) + 1

    asyncio.run(run())


def test_house_version_bumps(repo: Repository) -> None:
    async def run() -> None:
        assert await repo.house_version("h1") == 0
        await repo.save_visits([mkvisit("v1", 1000, house_id="h1")])
        assert await repo.house_version("h1") == 1
        await repo.save_visits([mkvisit("v1", 1000, house_id="h1")])  # identical: no bump
        assert await repo.house_version("h1") == 1
        await repo.save_visits([replace(mkvisit("v1", 1000, house_id="h1"), description="new")])
        assert await repo.house_version("h1") == 2
        assert await repo.bump_version("h1") == 3

    asyncio.run(run())


def test_cursor_roundtrip(repo: Repository) -> None:
    async def run() -> None:
        assert await repo.get_cursor("d1") is None
        await repo.set_cursor("d1", 500)
        assert await repo.get_cursor("d1") == 500
        await repo.set_cursor("d1", 900)
        assert await repo.get_cursor("d1") == 900
        assert await repo.get_cursor("other") is None

    asyncio.run(run())


def test_device_state_roundtrip(repo: Repository) -> None:
    async def run() -> None:
        assert await repo.get_device_state("d1") is None
        state = DeviceState(
            porch=PorchState(),
            pending_event_ids=("e1", "e2"),
            pending_events=(),
        )
        await repo.set_device_state("d1", state)
        assert await repo.get_device_state("d1") == state

    asyncio.run(run())


def test_visit_kinds_survive(repo: Repository) -> None:
    async def run() -> None:
        visit = replace(mkvisit("v1", 1000, house_id="h1"), kind=VisitKind.BOX_GONE)
        await repo.save_visits([visit])
        assert await repo.get_visit("v1") == visit

    asyncio.run(run())
