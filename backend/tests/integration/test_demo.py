import asyncio
import socket
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from porch.adapters.tape import load_tape
from porch.api.app import create_app
from porch.config import Settings
from porch.demo import demo_context, ingest_tape
from tests.helpers import DEMO_FIXTURE, REPO_ROOT

TAPE_DIR = REPO_ROOT / "fixtures" / "tapes" / "synthetic-day"
LOOPBACK = {"127.0.0.1", "::1", "localhost"}


class _NetworkBlockedError(OSError):
    pass


@pytest.fixture(autouse=True)
def no_network(monkeypatch: pytest.MonkeyPatch) -> None:
    """Block outbound connects; loopback stays so asyncio self-pipes work."""
    real_connect = socket.socket.connect

    def guarded(sock: socket.socket, address: Any, *rest: Any) -> Any:
        host = address[0] if isinstance(address, tuple) else address
        if host not in LOOPBACK:
            raise _NetworkBlockedError(host)
        return real_connect(sock, address, *rest)

    monkeypatch.setattr(socket.socket, "connect", guarded)


def test_demo_day(tmp_path: Path) -> None:
    tape = load_tape(TAPE_DIR)
    ctx = demo_context(tape, Settings(), tmp_path, DEMO_FIXTURE)
    asyncio.run(ingest_tape(ctx, tape))
    with TestClient(create_app(ctx)) as client:
        response = client.get("/v1/houses/demo/visits", params={"day": "2026-06-01"})
    assert response.status_code == 200
    body = response.json()
    assert sorted(c["kind"] for c in body["cards"]) == [
        "box_gone",
        "car_stopped",
        "delivery",
        "delivery",
        "visitor",
    ]
    assert body["folded"]["cars_passed"] == 2
    assert body["folded"]["activity"] == 0
    deliveries = [c for c in body["cards"] if c["kind"] == "delivery"]
    priya = [c for c in deliveries if "Box for Priya Shah" in c["facts"]]
    assert len(priya) == 1
    jo = [c for c in deliveries if "Leaning on the door" in c["facts"]]
    assert len(jo) == 1
    assert "Box for Jo Lindqvist" in jo[0]["facts"]
