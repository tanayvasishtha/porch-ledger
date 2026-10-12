"""Ring adapter tests: MockTransport client, source, fetcher, recorder, webhook."""

import asyncio
import hashlib
import hmac
import json
from pathlib import Path
from typing import Any

import httpx2
import pytest
from fastapi.testclient import TestClient

from porch.adapters.cassette import Cassette
from porch.adapters.local import FileMediaStore
from porch.adapters.ring import (
    RingClient,
    RingMediaFetcher,
    RingSource,
    WebhookSignatureError,
    parse_webhook,
    verify_signature,
)
from porch.adapters.ring.recorder import TapeRecorder
from porch.adapters.tape import load_tape
from porch.api.app import create_app
from porch.api.deps import AppContext
from porch.cli import main
from porch.config import RingSettings, Settings
from porch.domain import DoorEvent
from porch.ports import PortError
from tests.helpers import FakeClock, FakeRepo, demo_house

TOKEN = "test-token-abc"
DEVICE = "doorbell-1"


def _settings(**ring: Any) -> Settings:
    return Settings(ring=RingSettings(**ring))


def _client(handler: Any, **ring: Any) -> RingClient:
    http = httpx2.AsyncClient(
        base_url="https://api.amazonvision.com", transport=httpx2.MockTransport(handler)
    )
    return RingClient(_settings(**ring), TOKEN, client=http, sleep=_noop_sleep)


async def _noop_sleep(_seconds: float) -> None:
    pass


def _history_page(events: list[dict[str, Any]], next_url: str | None = None) -> dict[str, Any]:
    page: dict[str, Any] = {"data": events, "links": {}}
    if next_url is not None:
        page["links"] = {"next": next_url}
    return page


def _history_event(eid: str, start: int, end: int, event_type: str = "motion") -> dict[str, Any]:
    return {
        "type": "history-events",
        "id": eid,
        "attributes": {"event_type": event_type, "start": start, "end": end},
        "relationships": {"source": {"data": {"type": "devices", "id": DEVICE}}},
    }


# --- RingClient -------------------------------------------------------------


def test_history_paginates_and_filters_since(tmp_path: Path) -> None:
    next_url = f"/v1/history/devices/{DEVICE}/events?page[key]=2026-01-01T00:00:00Z"
    page1 = _history_page(
        [_history_event("e3", 300, 400), _history_event("e2", 200, 250)], next_url
    )
    page2 = _history_page([_history_event("e1", 100, 150), _history_event("e0", 50, 60)])
    seen: list[str] = []

    def handler(request: httpx2.Request) -> httpx2.Response:
        seen.append(str(request.url))
        assert request.headers["authorization"] == f"Bearer {TOKEN}"
        if "page[key]" in str(request.url):
            return httpx2.Response(200, json=page2)
        return httpx2.Response(200, json=page1)

    client = _client(handler)
    events = asyncio.run(client.history(DEVICE, since_ms=75))
    assert [e.id for e in events] == ["e1", "e2", "e3"]
    assert len(seen) == 2  # both pages fetched


def test_history_stops_at_page_limit(tmp_path: Path) -> None:
    calls = 0

    def handler(request: httpx2.Request) -> httpx2.Response:
        nonlocal calls
        calls += 1
        return httpx2.Response(200, json=_history_page([], "/next"))

    client = _client(handler, history_page_limit=2)
    assert asyncio.run(client.history(DEVICE, since_ms=0)) == []
    assert calls == 2


def test_snapshot_303_drops_bearer_on_presigned_host(tmp_path: Path) -> None:
    signed_headers: dict[str, str] = {}

    def handler(request: httpx2.Request) -> httpx2.Response:
        if request.method == "POST":
            return httpx2.Response(
                303, headers={"location": "https://download-x.amazonaws.com/get?sig=1"}
            )
        signed_headers.update(dict(request.headers))
        return httpx2.Response(200, content=b"jpeg-bytes")

    client = _client(handler)
    assert asyncio.run(client.snapshot(DEVICE, 1000)) == b"jpeg-bytes"
    assert "authorization" not in signed_headers


def test_snapshot_404_returns_none(tmp_path: Path) -> None:
    def handler(request: httpx2.Request) -> httpx2.Response:
        return httpx2.Response(404, json={"errors": [{"code": "NOT_FOUND"}]})

    client = _client(handler)
    assert asyncio.run(client.snapshot(DEVICE, 1000)) is None


def test_snapshot_422_undecryptable_returns_none(tmp_path: Path) -> None:
    """Playground answers 422 GRECO_NO_VALID_KEY for a frame it cannot decrypt."""

    def handler(request: httpx2.Request) -> httpx2.Response:
        return httpx2.Response(422, json={"errors": [{"code": "GRECO_NO_VALID_KEY"}]})

    client = _client(handler)
    assert asyncio.run(client.snapshot(DEVICE, 1000)) is None


def test_snapshot_presigned_422_returns_none(tmp_path: Path) -> None:
    def handler(request: httpx2.Request) -> httpx2.Response:
        if request.method == "POST":
            return httpx2.Response(
                303, headers={"location": "https://download-x.amazonaws.com/get?sig=1"}
            )
        return httpx2.Response(422, json={"errors": [{"code": "GRECO_NO_VALID_KEY"}]})

    client = _client(handler)
    assert asyncio.run(client.snapshot(DEVICE, 1000)) is None


def test_clip_303_drops_bearer_on_presigned_host(tmp_path: Path) -> None:
    signed_headers: dict[str, str] = {}

    def handler(request: httpx2.Request) -> httpx2.Response:
        if request.method == "POST":
            return httpx2.Response(
                303, headers={"location": "https://download-x.amazonaws.com/clip?sig=1"}
            )
        signed_headers.update(dict(request.headers))
        return httpx2.Response(200, content=b"clip-mp4")

    client = _client(handler)
    assert asyncio.run(client.clip(DEVICE, 1000, 2000)) == b"clip-mp4"
    assert "authorization" not in signed_headers


def test_clip_422_undecryptable_returns_none(tmp_path: Path) -> None:
    def handler(request: httpx2.Request) -> httpx2.Response:
        return httpx2.Response(422, json={"errors": [{"code": "GRECO_NO_VALID_KEY"}]})

    client = _client(handler, media_retry_schedule_s=(0,))
    assert asyncio.run(client.clip(DEVICE, 1000, 2000)) is None


def test_clip_303_without_location_returns_none(tmp_path: Path) -> None:
    def handler(request: httpx2.Request) -> httpx2.Response:
        return httpx2.Response(303)

    client = _client(handler, media_retry_schedule_s=(0,))
    assert asyncio.run(client.clip(DEVICE, 1000, 2000)) is None


def test_clip_statuses_and_retry_schedule(tmp_path: Path) -> None:
    statuses = iter([200, 206, 416, 416, 200])
    seen: list[int] = []

    def handler(request: httpx2.Request) -> httpx2.Response:
        status = next(statuses)
        seen.append(status)
        if status in (200, 206):
            return httpx2.Response(status, content=b"mp4")
        return httpx2.Response(status, json={"errors": [{"code": "MEDIA_NOT_FOUND"}]})

    client = _client(handler, media_retry_schedule_s=(0, 0, 0))
    assert asyncio.run(client.clip(DEVICE, 1000, 2000)) == b"mp4"  # 200
    assert asyncio.run(client.clip(DEVICE, 1000, 2000)) == b"mp4"  # 206
    assert asyncio.run(client.clip(DEVICE, 1000, 2000)) == b"mp4"  # 416,416 then 200
    assert seen == [200, 206, 416, 416, 200]


def test_clip_exhaustion_returns_none(tmp_path: Path) -> None:
    def handler(request: httpx2.Request) -> httpx2.Response:
        return httpx2.Response(425, json={"errors": [{"code": "RECORDING_NOT_READY"}]})

    client = _client(handler, media_retry_schedule_s=(0, 0))
    assert asyncio.run(client.clip(DEVICE, 1000, 2000)) is None  # 1 + 2 attempts, all 425


def test_429_honours_retry_after_once(tmp_path: Path) -> None:
    calls = 0

    def handler(request: httpx2.Request) -> httpx2.Response:
        nonlocal calls
        calls += 1
        if calls == 1:
            return httpx2.Response(429, headers={"retry-after": "0"})
        return httpx2.Response(200, json=_history_page([]))

    client = _client(handler)
    assert asyncio.run(client.history(DEVICE, 0)) == []
    assert calls == 2


def test_error_status_is_port_error_without_token(tmp_path: Path) -> None:
    def handler(request: httpx2.Request) -> httpx2.Response:
        return httpx2.Response(403, json={"errors": [{"code": "REQUEST_FORBIDDEN"}]})

    client = _client(handler)
    with pytest.raises(PortError) as exc:
        asyncio.run(client.history(DEVICE, 0))
    assert str(exc.value) == "ring.history: 403 REQUEST_FORBIDDEN"
    assert TOKEN not in str(exc.value)


# --- RingSource / RingMediaFetcher -------------------------------------------


def test_ring_source_maps_events_and_advances_cursor(tmp_path: Path) -> None:
    page = _history_page(
        [
            _history_event("e2", 200, 260, "ding"),
            _history_event("e1", 100, 160, "motion"),
        ]
    )
    client = _client(lambda request: httpx2.Response(200, json=page))
    repo = FakeRepo()
    source = RingSource(client, DEVICE, repo, Cassette(tmp_path, "live"))

    events = asyncio.run(source.poll())
    assert [(e.id, e.kind, e.provenance) for e in events] == [
        ("e1", "motion", "ring"),
        ("e2", "ding", "ring"),
    ]
    assert repo._cursors[DEVICE] == 260

    # Second poll re-requests with since=cursor; the same events are filtered.
    again = asyncio.run(source.poll())
    assert again == []
    assert repo._cursors[DEVICE] == 260


def test_ring_media_fetcher_offsets_clamping_and_clip(tmp_path: Path) -> None:
    def handler(request: httpx2.Request) -> httpx2.Response:
        if "media/image/download" in str(request.url):
            body = json.loads(request.content)
            return httpx2.Response(
                303,
                headers={"location": f"https://dl.x/img?at={body['timestamp']}"},
            )
        if "media/video/download" in str(request.url):
            return httpx2.Response(200, content=b"clip-mp4")
        return httpx2.Response(200, content=b"jpeg")

    clock = FakeClock(2_500)
    client = _client(handler)
    fetcher = RingMediaFetcher(client, DEVICE, _settings(), Cassette(tmp_path, "live"), clock)
    event = DoorEvent(
        id="e1",
        device_id=DEVICE,
        kind="motion",
        sub_type="human",
        start_ms=1_000,
        end_ms=3_000,
        provenance="ring",
    )
    snaps = asyncio.run(fetcher.snapshots(event))
    assert [s.at_ms for s in snaps] == [1_000, 2_000, 2_500]  # clamped to now
    assert all(s.detections is None and s.suffix == ".jpg" for s in snaps)
    clip = asyncio.run(fetcher.clip(event))
    assert clip is not None and clip.data == b"clip-mp4" and clip.suffix == ".mp4"


def test_ring_media_fetcher_no_media(tmp_path: Path) -> None:
    def handler(request: httpx2.Request) -> httpx2.Response:
        if "media/image" in str(request.url):
            return httpx2.Response(404, json={})
        return httpx2.Response(416, json={})

    clock = FakeClock(5_000)
    client = _client(handler, media_retry_schedule_s=(0,))
    fetcher = RingMediaFetcher(client, DEVICE, _settings(), Cassette(tmp_path, "live"), clock)
    event = DoorEvent(
        id="e1",
        device_id=DEVICE,
        kind="motion",
        sub_type=None,
        start_ms=1_000,
        end_ms=2_000,
        provenance="ring",
    )
    assert asyncio.run(fetcher.snapshots(event)) == []
    assert asyncio.run(fetcher.clip(event)) is None


# --- TapeRecorder -------------------------------------------------------------


def test_recorder_writes_loadable_tape(tmp_path: Path) -> None:
    page = _history_page([_history_event("e1", 1_000, 2_000, "ding")])

    def handler(request: httpx2.Request) -> httpx2.Response:
        if "events" in str(request.url):
            return httpx2.Response(200, json=page)
        if "media/image" in str(request.url):
            return httpx2.Response(303, headers={"location": "https://dl.x/img"})
        if "media/video" in str(request.url):
            return httpx2.Response(200, content=b"mp4-bytes")
        return httpx2.Response(200, content=b"jpeg")

    clock = FakeClock(0)
    lines: list[str] = []

    async def advancing_sleep(seconds: float) -> None:
        clock.current += int(seconds * 1000)

    recorder = TapeRecorder(
        client=_client(handler),
        settings=_settings(poll_interval_s=30),
        device_id=DEVICE,
        repo=FakeRepo(),
        cassette=Cassette(tmp_path / "cassette", "live"),
        clock=clock,
    )
    events = asyncio.run(
        recorder.record(
            minutes=1,
            out_dir=tmp_path / "tape",
            sleep=advancing_sleep,
            emit=lines.append,
        )
    )
    assert len(events) == 1 and any("e1" in line for line in lines)
    tape = load_tape(tmp_path / "tape")
    assert tape.provenance == "ring"
    assert [e.id for e in tape.events] == ["e1"]
    assert len(tape.snapshots) == 3  # three offsets fetched
    assert all(s.detections is None for s in tape.snapshots)
    assert tape.clips[0].file.endswith(".mp4")
    for snap in tape.snapshots:
        assert (tmp_path / "tape" / snap.file).read_bytes() == b"jpeg"


# --- Webhook ------------------------------------------------------------------


SECRET = "signing-key"

MOTION_BODY = json.dumps(
    {
        "meta": {
            "version": "1.1",
            "time": "2026-02-13T13:39:57.200155525Z",
            "request_id": "2ad45ade-1818-4154-813b-afdd8bcd8085",
            "account_id": "ava1.ring.account.XXXYYY",
        },
        "data": {
            "id": f"{DEVICE}_motion_1786715596787",
            "type": "motion_detected",
            "attributes": {
                "source": DEVICE,
                "source_type": "devices",
                "timestamp": 1786715596787,
                "timestamp_readable": "2026-08-14 08:53:16",
                "sub_type": "human",
                "component_ids": ["0"],
            },
            "relationships": {"devices": {"links": {"self": f"/v1/devices/{DEVICE}"}}},
        },
    }
).encode()

PRESS_BODY = json.dumps(
    {
        "meta": {
            "version": "1.1",
            "time": "2026-02-14T00:02:53.027052438Z",
            "request_id": "c83081fc-2f1b-4cb7-8b18-b18a318b8bab",
            "account_id": "ava1.ring.account.XXXYYY",
        },
        "data": {
            "id": f"{DEVICE}_button_press_1771027372393",
            "type": "button_press",
            "attributes": {
                "source": DEVICE,
                "source_type": "devices",
                "timestamp": 1771027372393,
            },
            "relationships": {"devices": {"links": {"self": f"/v1/devices/{DEVICE}"}}},
        },
    }
).encode()

IGNORED_BODY = json.dumps(
    {
        "meta": {"version": "1.1"},
        "data": {
            "id": "sub1",
            "type": "subscription_activated",
            "attributes": {"source": "subscriptions"},
        },
    }
).encode()


def _sign(body: bytes, secret: str = SECRET) -> str:
    return "sha256=" + hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()


def test_verify_signature_accepts_valid() -> None:
    verify_signature({"X-Signature": _sign(MOTION_BODY)}, MOTION_BODY, SECRET)


def test_verify_signature_rejects() -> None:
    with pytest.raises(WebhookSignatureError):
        verify_signature({}, MOTION_BODY, SECRET)
    with pytest.raises(WebhookSignatureError):
        verify_signature({"X-Signature": "sha256=deadbeef"}, MOTION_BODY, SECRET)
    with pytest.raises(WebhookSignatureError):
        verify_signature({"X-Signature": _sign(b"tampered")}, MOTION_BODY, SECRET)
    with pytest.raises(WebhookSignatureError):
        verify_signature({"X-Signature": _sign(MOTION_BODY, "other-key")}, MOTION_BODY, SECRET)


def test_parse_webhook_maps_documented_payloads() -> None:
    motion = parse_webhook(MOTION_BODY)
    assert motion is not None
    assert motion.kind == "motion" and motion.sub_type == "human"
    assert motion.device_id == DEVICE and motion.start_ms == 1786715596787
    assert motion.provenance == "ring"
    press = parse_webhook(PRESS_BODY)
    assert press is not None and press.kind == "ding" and press.sub_type is None
    assert parse_webhook(IGNORED_BODY) is None
    assert parse_webhook(b"not json") is None


# --- Webhook route ------------------------------------------------------------


class _Sink:
    def __init__(self) -> None:
        self.events: list[DoorEvent] = []

    async def accept(self, event: DoorEvent) -> None:
        self.events.append(event)


def _webhook_client(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, sink: _Sink | None
) -> TestClient:
    monkeypatch.setenv("RING_WEBHOOK_SECRET", SECRET)
    monkeypatch.chdir(tmp_path)
    ctx = AppContext(
        settings=_settings(),
        repo=FakeRepo(),
        media=FileMediaStore(tmp_path / "media", ""),
        house=demo_house(),
        clock=FakeClock(0),
        sink=sink,
    )
    return TestClient(create_app(ctx))


def test_webhook_route_status_codes(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    sink = _Sink()
    client = _webhook_client(tmp_path, monkeypatch, sink)
    signed = {"X-Signature": _sign(MOTION_BODY)}

    response = client.post("/ring/webhook", content=MOTION_BODY, headers=signed)
    assert response.status_code == 202
    assert len(sink.events) == 1 and sink.events[0].kind == "motion"

    ignored = client.post(
        "/ring/webhook", content=IGNORED_BODY, headers={"X-Signature": _sign(IGNORED_BODY)}
    )
    assert ignored.status_code == 204

    bad = client.post("/ring/webhook", content=MOTION_BODY, headers={"X-Signature": "sha256=x"})
    assert bad.status_code == 401

    oversized = client.post("/ring/webhook", content=b"x" * (64 * 1024 + 1), headers=signed)
    assert oversized.status_code == 413


def test_webhook_route_no_sink_503(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    client = _webhook_client(tmp_path, monkeypatch, None)
    response = client.post(
        "/ring/webhook", content=MOTION_BODY, headers={"X-Signature": _sign(MOTION_BODY)}
    )
    assert response.status_code == 503


def test_record_cli_missing_token_exits_2(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: Any
) -> None:
    monkeypatch.delenv("RING_ACCESS_TOKEN", raising=False)
    monkeypatch.chdir(tmp_path)
    with pytest.raises(SystemExit) as exc:
        main(["record", "--minutes", "1", "--out", str(tmp_path / "tape")])
    assert exc.value.code == 2
    assert "RING_ACCESS_TOKEN" in capsys.readouterr().out


def test_webhook_route_no_secret_503(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("RING_WEBHOOK_SECRET", raising=False)
    monkeypatch.chdir(tmp_path)
    ctx = AppContext(
        settings=_settings(),
        repo=FakeRepo(),
        media=FileMediaStore(tmp_path / "media", ""),
        house=demo_house(),
        clock=FakeClock(0),
        sink=_Sink(),
    )
    client = TestClient(create_app(ctx))
    response = client.post(
        "/ring/webhook", content=MOTION_BODY, headers={"X-Signature": _sign(MOTION_BODY)}
    )
    assert response.status_code == 503
