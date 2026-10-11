import json
from pathlib import Path

from porch.cli import main


def test_export_contracts(tmp_path: Path) -> None:
    out = tmp_path / "contracts"
    main(["export-contracts", "--out", str(out)])
    openapi = json.loads((out / "openapi.json").read_text(encoding="utf-8"))
    assert "/v1/houses/{house_id}/visits" in openapi["paths"]
    tools = json.loads((out / "mcp-tools.json").read_text(encoding="utf-8"))
    names = {t["name"] for t in tools}
    assert names == {
        "anything_for_me",
        "todays_visits",
        "visit_detail",
        "claim_box",
        "residents",
        "ask",
    }
    for tool in tools:
        assert "input_schema" in tool or "inputSchema" in tool
