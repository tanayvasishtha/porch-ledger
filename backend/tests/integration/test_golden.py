"""Golden contract for API response bodies, shared with the TV app tests.

Regenerate with PORCH_UPDATE_GOLDEN=1; the test fails when the committed
files differ from what the backend produces.
"""

import asyncio
import json
import os
from pathlib import Path

from fastapi.testclient import TestClient

from porch.adapters.tape import load_tape
from porch.api.app import create_app
from porch.config import Settings
from porch.demo import demo_context, ingest_tape
from tests.helpers import DEMO_FIXTURE

REPO_ROOT = Path(__file__).resolve().parents[3]
TAPE_DIR = REPO_ROOT / "fixtures" / "tapes" / "synthetic-day"
GOLDEN_DIR = Path(__file__).resolve().parents[1] / "golden"
UPDATE = os.environ.get("PORCH_UPDATE_GOLDEN") == "1"
DEMO_DAY = "2026-06-01"


def _golden(name: str, body: object) -> None:
    path = GOLDEN_DIR / name
    text = json.dumps(body, indent=2, sort_keys=True) + "\n"
    if UPDATE:
        path.write_text(text, encoding="utf-8")
        return
    assert path.read_text(encoding="utf-8") == text


def test_golden_visit_bodies(tmp_path: Path) -> None:
    tape = load_tape(TAPE_DIR)
    ctx = demo_context(tape, Settings(), tmp_path, DEMO_FIXTURE)
    asyncio.run(ingest_tape(ctx, tape))
    with TestClient(create_app(ctx)) as client:
        listing = client.get(f"/v1/houses/demo/visits?day={DEMO_DAY}").json()
        priya = next(c for c in listing["cards"] if "Box for Priya Shah" in c["facts"])
        detail = client.get(f"/v1/visits/{priya['id']}").json()
    _golden("visit_list.json", listing)
    _golden("visit_detail.json", detail)
