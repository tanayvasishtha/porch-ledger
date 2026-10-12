import asyncio
import hashlib
from dataclasses import replace
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from fastapi.testclient import TestClient
from mcp import Client

from porch.adapters.local import FileMediaStore
from porch.api.app import create_app
from porch.api.deps import AppContext
from porch.config import ApiSettings, Settings
from porch.domain import Visit, VisitKind
from porch.mcp_server import build_mcp
from porch.ports import MediaStore
from tests.helpers import FakeClock, FakeRepo, demo_house, mkvisit

LA = ZoneInfo("America/Los_Angeles")


def mkctx(
    tmp_path: Path,
    visits: list[Visit] | None = None,
    api: ApiSettings | None = None,
    now_ms: int = 0,
    media: MediaStore | None = None,
) -> AppContext:
    settings = Settings(api=api or ApiSettings())
    return AppContext(
        settings=settings,
        repo=FakeRepo(visits),
        media=media or FileMediaStore(tmp_path / "media", settings.api.public_base_url),
        house=demo_house(),
        clock=FakeClock(now_ms),
    )


def client_for(ctx: AppContext) -> TestClient:
    return TestClient(create_app(ctx))


def test_etag_then_304(tmp_path: Path) -> None:
    ctx = mkctx(tmp_path)
    client = client_for(ctx)
    first = client.get("/v1/houses/demo/visits")
    assert first.status_code == 200
    etag = first.headers["etag"]
    assert etag.startswith('"v0-')
    assert first.headers["cache-control"] == "no-cache"
    again = client.get("/v1/houses/demo/visits", headers={"If-None-Match": etag})
    assert again.status_code == 304
    assert again.content == b""


def test_etag_changes_on_version_bump(tmp_path: Path) -> None:
    ctx = mkctx(tmp_path)
    client = client_for(ctx)
    first = client.get("/v1/houses/demo/visits")
    asyncio.run(ctx.repo.bump_version("demo"))
    second = client.get("/v1/houses/demo/visits", headers={"If-None-Match": first.headers["etag"]})
    assert second.status_code == 200
    assert second.headers["etag"] != first.headers["etag"]


def test_folded_counts(tmp_path: Path) -> None:
    day_start = int(datetime(2026, 6, 1, tzinfo=LA).timestamp() * 1000)
    visits = [
        mkvisit("d1", day_start + 1000, VisitKind.DELIVERY),
        mkvisit("c1", day_start + 2000, VisitKind.CARS_PASSED),
        mkvisit("a1", day_start + 3000, VisitKind.ACTIVITY),
    ]
    client = client_for(mkctx(tmp_path, visits))
    body = client.get("/v1/houses/demo/visits?day=2026-06-01").json()
    assert [c["id"] for c in body["cards"]] == ["d1"]
    assert body["folded"] == {"cars_passed": 1, "activity": 1}


def test_day_boundaries_dst_spring_forward(tmp_path: Path) -> None:
    inside = int(datetime(2026, 3, 8, 20, 0, tzinfo=ZoneInfo("UTC")).timestamp() * 1000)
    before = int(datetime(2026, 3, 8, 7, 0, tzinfo=ZoneInfo("UTC")).timestamp() * 1000)
    next_midnight = int(datetime(2026, 3, 9, 7, 0, tzinfo=ZoneInfo("UTC")).timestamp() * 1000)
    visits = [
        mkvisit("before", before, VisitKind.DELIVERY),
        mkvisit("inside", inside, VisitKind.DELIVERY),
        mkvisit("after", next_midnight, VisitKind.DELIVERY),
    ]
    client = client_for(mkctx(tmp_path, visits))
    body = client.get("/v1/houses/demo/visits?day=2026-03-08").json()
    assert [c["id"] for c in body["cards"]] == ["inside"]


def test_day_boundaries_dst_fall_back(tmp_path: Path) -> None:
    last_ms_of_day = int(datetime(2026, 11, 2, tzinfo=LA).timestamp() * 1000 - 1)
    visits = [mkvisit("late", last_ms_of_day, VisitKind.DELIVERY)]
    client = client_for(mkctx(tmp_path, visits))
    body = client.get("/v1/houses/demo/visits?day=2026-11-01").json()
    assert [c["id"] for c in body["cards"]] == ["late"]


def test_claim_visit(tmp_path: Path) -> None:
    ctx = mkctx(tmp_path, [mkvisit("v1", 1000, VisitKind.DELIVERY)])
    client = client_for(ctx)
    response = client.post("/v1/visits/v1/claim", json={"resident_id": "priya"})
    assert response.status_code == 200
    card = response.json()
    assert card["claimed_by"] == "priya"
    assert card["version"] == 2


def test_claim_unknown_resident_and_visit(tmp_path: Path) -> None:
    ctx = mkctx(tmp_path, [mkvisit("v1", 1000, VisitKind.DELIVERY)])
    client = client_for(ctx)
    bad_resident = client.post("/v1/visits/v1/claim", json={"resident_id": "ghost"})
    assert bad_resident.status_code == 422
    assert bad_resident.headers["content-type"].startswith("application/problem+json")
    missing = client.post("/v1/visits/nope/claim", json={"resident_id": "priya"})
    assert missing.status_code == 404


def test_claim_body_validation_problem(tmp_path: Path) -> None:
    ctx = mkctx(tmp_path, [mkvisit("v1", 1000, VisitKind.DELIVERY)])
    client = client_for(ctx)
    response = client.post("/v1/visits/v1/claim", json={})
    assert response.status_code == 422
    assert response.headers["content-type"].startswith("application/problem+json")


def test_auth_open_by_default(tmp_path: Path) -> None:
    client = client_for(mkctx(tmp_path))
    assert client.get("/v1/houses/demo/visits").status_code == 200


def test_auth_required(tmp_path: Path) -> None:
    key = hashlib.sha256(b"s3cret").hexdigest()
    ctx = mkctx(tmp_path, api=ApiSettings(house_key_sha256=key))
    client = client_for(ctx)
    assert client.get("/v1/houses/demo/visits").status_code == 401
    assert (
        client.get("/v1/houses/demo/visits", headers={"Authorization": "Bearer wrong"}).status_code
        == 401
    )
    ok = client.get("/v1/houses/demo/visits", headers={"Authorization": "Bearer s3cret"})
    assert ok.status_code == 200
    assert client.get("/healthz").status_code == 200


def test_unknown_house_404(tmp_path: Path) -> None:
    client = client_for(mkctx(tmp_path))
    response = client.get("/v1/houses/nope/visits")
    assert response.status_code == 404
    assert response.headers["content-type"].startswith("application/problem+json")


def test_media_served_and_traversal_rejected(tmp_path: Path) -> None:
    ctx = mkctx(tmp_path)
    key = asyncio.run(ctx.media.put(b"img", ".png"))
    client = client_for(ctx)
    response = client.get(f"/v1/media/{key}")
    assert response.status_code == 200
    assert response.content == b"img"
    assert response.headers["content-type"] == "image/png"
    assert client.get("/v1/media/../secrets").status_code == 404
    assert client.get("/v1/media/missing-key").status_code == 404


def test_visit_detail_and_residents(tmp_path: Path) -> None:
    ctx = mkctx(tmp_path, [mkvisit("v1", 1000, VisitKind.DELIVERY)])
    client = client_for(ctx)
    detail = client.get("/v1/visits/v1")
    assert detail.status_code == 200
    assert detail.json()["id"] == "v1"
    assert client.get("/v1/visits/nope").status_code == 404
    residents = client.get("/v1/houses/demo/residents")
    assert residents.status_code == 200
    assert [r["id"] for r in residents.json()] == ["priya", "sam", "jo"]


def test_cors_preflight_on_mcp(tmp_path: Path) -> None:
    ctx = mkctx(tmp_path, api=ApiSettings(cors_origins=("http://localhost:5173",)))
    client = client_for(ctx)
    response = client.options(
        "/mcp",
        headers={
            "Origin": "http://localhost:5173",
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "content-type, mcp-protocol-version",
        },
    )
    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == "http://localhost:5173"
    assert "mcp-protocol-version" in response.headers["access-control-allow-headers"]


def test_mcp_lists_house_info_tool(tmp_path: Path) -> None:
    """The Echo client needs the house header over MCP, no REST."""

    async def tools() -> list[str]:
        async with Client(build_mcp(mkctx(tmp_path))) as mcp:
            result = await mcp.list_tools()
        return [t.name for t in result.tools]

    assert "house_info" in asyncio.run(tools())


class _FakeSpeech:
    def __init__(self, media: MediaStore) -> None:
        self._media = media
        self.calls: list[str] = []

    async def synthesize(self, text: str) -> str:
        self.calls.append(text)
        return await self._media.put(b"mp3-bytes", ".mp3")


def test_speech_not_configured_404(tmp_path: Path) -> None:
    client = client_for(mkctx(tmp_path))
    out = client.post("/v1/speech", json={"text": "hello"})
    assert out.status_code == 404
    assert "speech is not configured" in out.json()["detail"]


def test_speech_returns_media_url(tmp_path: Path) -> None:
    ctx = mkctx(tmp_path)
    speech = _FakeSpeech(ctx.media)
    ctx = AppContext(
        settings=ctx.settings,
        repo=ctx.repo,
        media=ctx.media,
        house=ctx.house,
        clock=ctx.clock,
        speech=speech,
    )
    client = client_for(ctx)
    out = client.post("/v1/speech", json={"text": "You have a box."})
    assert out.status_code == 200
    url = out.json()["url"]
    assert url.endswith(".mp3")
    assert speech.calls == ["You have a box."]
    served = client.get(url)
    assert served.status_code == 200
    assert served.content == b"mp3-bytes"


def test_speech_rejects_long_text(tmp_path: Path) -> None:
    client = client_for(mkctx(tmp_path))
    out = client.post("/v1/speech", json={"text": "x" * 301})
    assert out.status_code == 422


class SignedMedia(FileMediaStore):
    """S3-style store: url() hands out a signed link, not a local path."""

    async def url(self, key: str, ttl_s: int) -> str:
        return f"https://signed.example/{key}?sig=x{ttl_s}"


def test_etag_rolls_with_the_media_url_ttl(tmp_path: Path) -> None:
    ctx = mkctx(tmp_path, api=ApiSettings(media_url_ttl_s=60))
    client = client_for(ctx)
    first = client.get("/v1/houses/demo/visits")
    assert first.status_code == 200
    etag = first.headers["etag"]
    again = client.get("/v1/houses/demo/visits", headers={"If-None-Match": etag})
    assert again.status_code == 304
    # Half the TTL later the bucket rolls even with the version unchanged.
    clock = ctx.clock
    assert isinstance(clock, FakeClock)
    clock.current += 30_001
    rolled = client.get("/v1/houses/demo/visits", headers={"If-None-Match": etag})
    assert rolled.status_code == 200
    assert rolled.headers["etag"] != etag


def test_media_urls_come_from_the_store(tmp_path: Path) -> None:
    visit = replace(
        mkvisit("v1", 1_000, VisitKind.DELIVERY),
        hero_media_key="hero.jpg",
        clip_media_key="clip.mp4",
    )
    ctx = mkctx(tmp_path, visits=[visit], media=SignedMedia(tmp_path / "media", ""))
    client = client_for(ctx)
    card = client.get("/v1/houses/demo/visits").json()["cards"][0]
    assert card["hero_url"] == "https://signed.example/hero.jpg?sig=x600"
    assert card["clip_url"] == "https://signed.example/clip.mp4?sig=x600"
    detail = client.get("/v1/visits/v1").json()
    assert detail["hero_url"] == "https://signed.example/hero.jpg?sig=x600"
    claimed = client.post("/v1/visits/v1/claim", json={"resident_id": "priya"}).json()
    assert claimed["hero_url"] == "https://signed.example/hero.jpg?sig=x600"
