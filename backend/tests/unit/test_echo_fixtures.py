"""Echo client fixtures must match what the MCP tools emit today.

Regenerate with `just echo-fixtures`; this test fails on drift, the same
role as the TV goldens.
"""

import asyncio
import json

from porch.demo import echo_fixtures, repo_root

FIXTURES = repo_root() / "echo" / "src" / "__fixtures__"


def test_echo_fixtures_match_tool_outputs() -> None:
    """Committed echo fixtures equal a fresh generation."""
    generated = asyncio.run(echo_fixtures())
    for name, content in generated.items():
        committed = json.loads((FIXTURES / name).read_text(encoding="utf-8"))
        assert committed == content, f"{name} drifted: run just echo-fixtures"


def test_fixture_files_exist() -> None:
    names = {"house-info.json", "inbox-priya.json", "inbox-sam.json", "claim-box.json"}
    assert {p.name for p in FIXTURES.glob("*.json")} >= names
