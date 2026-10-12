import asyncio
import hashlib
from dataclasses import replace
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import httpx2
from fastapi import FastAPI
from mcp import Client
from mcp.client._transport import Transport
from mcp.client.streamable_http import streamable_http_client

from porch.api.app import create_app
from porch.api.deps import AppContext
from porch.config import ApiSettings
from porch.domain import BoxFacts, NormBox, Visit, VisitKind
from tests.helpers import FakeRepo, mkvisit
from tests.unit.test_api import SignedMedia, mkctx

TOOL_NAMES = {"anything_for_me", "todays_visits", "visit_detail", "claim_box", "house_info", "ask"}
READ_TOOLS = {
    "anything_for_me",
    "todays_visits",
    "visit_detail",
    "house_info",
    "ask",
}

NOW_MS = int(datetime(2026, 6, 1, 19, 0, tzinfo=ZoneInfo("UTC")).timestamp() * 1000)


def delivery_for(resident_id: str) -> Visit:
    visit = mkvisit(f"del-{resident_id}", NOW_MS - 3_600_000, VisitKind.DELIVERY)
    return replace(
        visit,
        box=BoxFacts(
            box=NormBox(x=0.1, y=0.4, w=0.2, h=0.2),
            recipient_id=resident_id,
            recipient_state="matched",
            blocks_door=False,
            door_overlap=None,
        ),
    )


def mkclient(app: FastAPI) -> tuple[httpx2.AsyncClient, Transport]:
    transport = httpx2.ASGITransport(app=app)
    http = httpx2.AsyncClient(
        transport=transport,
        base_url="http://localhost:8000",
        timeout=httpx2.Timeout(30.0, read=300.0),
    )
    return http, streamable_http_client("http://localhost:8000/mcp", http_client=http)


def seeded_ctx(tmp_path: Path, api: ApiSettings | None = None) -> AppContext:
    visits = [
        delivery_for("priya"),
        delivery_for("sam"),
        mkvisit("car1", NOW_MS - 7_200_000, VisitKind.CARS_PASSED),
    ]
    return mkctx(tmp_path, visits, api=api, now_ms=NOW_MS)


def test_tools_contract_and_call(tmp_path: Path) -> None:
    ctx = seeded_ctx(tmp_path)
    app = create_app(ctx)

    async def scenario() -> None:
        async with app.state.mcp.session_manager.run():
            http, transport = mkclient(app)
            async with http, Client(transport, mode="legacy") as client:
                tools = await client.list_tools()
                by_name = {t.name: t for t in tools.tools}
                assert set(by_name) == TOOL_NAMES
                for name in READ_TOOLS:
                    annotations = by_name[name].annotations
                    assert annotations is not None
                    assert annotations.read_only_hint
                assert client.protocol_version is not None
                assert client.protocol_version >= "2025-11-25"
                result = await client.call_tool("anything_for_me", {"resident_id": "priya"})
                assert not result.is_error
                content = result.structured_content
                assert content["spoken"].startswith("You have a box")
                assert len(content["items"]) == 1
                detail = await client.call_tool("visit_detail", {"visit_id": "del-priya"})
                assert not detail.is_error
                assert detail.structured_content["id"] == "del-priya"
                missing = await client.call_tool("visit_detail", {"visit_id": "nope"})
                assert missing.is_error
                claimed = await client.call_tool(
                    "claim_box",
                    {"visit_id": "del-priya", "resident_id": "priya"},
                )
                assert not claimed.is_error
                assert claimed.structured_content["claimed_by"] == "priya"
                bad = await client.call_tool(
                    "claim_box",
                    {"visit_id": "del-priya", "resident_id": "ghost"},
                )
                assert bad.is_error

    asyncio.run(scenario())


def test_protocol_2025_11_25_requested(tmp_path: Path) -> None:
    ctx = seeded_ctx(tmp_path)
    app = create_app(ctx)

    async def scenario() -> None:
        async with app.state.mcp.session_manager.run():
            http, transport = mkclient(app)
            async with http, Client(transport, mode="legacy") as client:
                assert client.protocol_version == "2025-11-25"
                tools = await client.list_tools()
                assert {t.name for t in tools.tools} == TOOL_NAMES

    asyncio.run(scenario())


def test_mcp_requires_key_when_configured(tmp_path: Path) -> None:
    key = hashlib.sha256(b"s3cret").hexdigest()
    ctx = seeded_ctx(tmp_path, api=ApiSettings(house_key_sha256=key))
    app = create_app(ctx)

    async def scenario() -> None:
        async with app.state.mcp.session_manager.run():
            http, _transport = mkclient(app)
            async with http:
                rejected = await http.post("http://localhost:8000/mcp", json={})
                assert rejected.status_code == 401
                good = httpx2.AsyncClient(
                    transport=httpx2.ASGITransport(app=app),
                    base_url="http://localhost:8000",
                    headers={"Authorization": "Bearer s3cret"},
                    timeout=httpx2.Timeout(30.0, read=300.0),
                )
                async with good:
                    transport = streamable_http_client(
                        "http://localhost:8000/mcp", http_client=good
                    )
                    async with Client(transport, mode="legacy") as client:
                        tools = await client.list_tools()
                        assert {t.name for t in tools.tools} == TOOL_NAMES

    asyncio.run(scenario())


def test_todays_visits_tool(tmp_path: Path) -> None:
    ctx = seeded_ctx(tmp_path)
    app = create_app(ctx)

    async def scenario() -> None:
        async with app.state.mcp.session_manager.run():
            http, transport = mkclient(app)
            async with http, Client(transport, mode="legacy") as client:
                all_visits = await client.call_tool("todays_visits", {})
                assert not all_visits.is_error
                ids = [c["id"] for c in all_visits.structured_content["result"]]
                assert set(ids) == {"del-priya", "del-sam"}
                cars = await client.call_tool("todays_visits", {"kind": "cars_passed"})
                car_ids = [c["id"] for c in cars.structured_content["result"]]
                assert car_ids == ["car1"]

    asyncio.run(scenario())


def test_signed_media_urls_reach_mcp_items(tmp_path: Path) -> None:
    """anything_for_me items carry the store-signed URL, not /v1/media."""
    visit = replace(
        delivery_for("priya"),
        hero_media_key="hero.jpg",
        clip_media_key="clip.mp4",
    )
    ctx = seeded_ctx(tmp_path)
    ctx = AppContext(
        settings=ctx.settings,
        repo=FakeRepo([visit]),
        media=SignedMedia(tmp_path / "media", ""),
        house=ctx.house,
        clock=ctx.clock,
    )
    app = create_app(ctx)

    async def scenario() -> None:
        async with app.state.mcp.session_manager.run():
            http, transport = mkclient(app)
            async with http, Client(transport, mode="legacy") as client:
                result = await client.call_tool("anything_for_me", {"resident_id": "priya"})
                item = result.structured_content["items"][0]
                assert item["hero_url"] == "https://signed.example/hero.jpg?sig=x600"
                assert item["clip_url"] == "https://signed.example/clip.mp4?sig=x600"
                detail = await client.call_tool("visit_detail", {"visit_id": visit.id})
                assert detail.structured_content["hero_url"].startswith("https://signed.example/")

    asyncio.run(scenario())
