"""Command line: serve the REST/MCP app, or export API contracts."""

import argparse
import asyncio
import json
import shutil
import time
from pathlib import Path
from typing import Any

import uvicorn
from mcp import Client
from mcp.server import MCPServer

from porch.adapters.local import FileMediaStore, SqliteRepository
from porch.adapters.local.house_file import load_house
from porch.adapters.tape import load_tape
from porch.api.app import create_app
from porch.api.days import day_bounds, today
from porch.api.deps import AppContext
from porch.config import Settings
from porch.demo import card_lines, demo_clock, ingest_tape


class SystemClock:
    """Wall clock for real deployments."""

    def now_ms(self) -> int:
        return int(time.time() * 1000)


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[3]


def _resolve_input(path: Path) -> Path:
    """Input fixtures resolve relative to cwd, then the repo root."""
    if path.is_absolute() or path.exists():
        return path
    return _repo_root() / path


def _build_ctx(settings: Settings) -> AppContext:
    return AppContext(
        settings=settings,
        repo=SqliteRepository(settings.api.sqlite_path),
        media=FileMediaStore(settings.api.local_media_dir, settings.api.public_base_url),
        house=load_house(_resolve_input(settings.api.house_file)),
        clock=SystemClock(),
    )


def _write_json(path: Path, data: object) -> None:
    path.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _serve(args: argparse.Namespace) -> None:
    app = create_app(_build_ctx(Settings()))
    uvicorn.run(app, host=args.host, port=args.port)


async def _tools_json(mcp: MCPServer) -> list[dict[str, Any]]:
    async with Client(mcp) as client:
        result = await client.list_tools()
    return [t.model_dump(mode="json", exclude_none=True) for t in result.tools]


def _export_contracts(args: argparse.Namespace) -> None:
    ctx = _build_ctx(Settings())
    app = create_app(ctx)
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    _write_json(out / "openapi.json", app.openapi())
    _write_json(out / "mcp-tools.json", asyncio.run(_tools_json(app.state.mcp)))


def _demo(args: argparse.Namespace) -> None:
    settings = Settings()
    tape = load_tape(_resolve_input(Path(args.tape)))
    # The demo owns .local; rebuild it from scratch every run.
    shutil.rmtree(settings.api.sqlite_path.parent, ignore_errors=True)
    ctx = AppContext(
        settings=settings,
        repo=SqliteRepository(settings.api.sqlite_path),
        media=FileMediaStore(settings.api.local_media_dir, settings.api.public_base_url),
        house=load_house(_resolve_input(settings.api.house_file)),
        clock=demo_clock(tape),
    )
    asyncio.run(ingest_tape(ctx, tape))
    day = today(ctx.house, ctx.clock)
    start_ms, end_ms = day_bounds(day, ctx.house)
    visits = asyncio.run(ctx.repo.visits_between(ctx.house.id, start_ms, end_ms))
    for line in card_lines(visits, ctx):
        print(line)
    if args.serve:
        uvicorn.run(create_app(ctx), host=args.host, port=args.port)


def main(argv: list[str] | None = None) -> None:
    """porch serve | porch export-contracts --out <dir>."""
    parser = argparse.ArgumentParser(prog="porch")
    sub = parser.add_subparsers(dest="command", required=True)
    serve = sub.add_parser("serve", help="run the API and MCP server")
    serve.add_argument("--host", default="127.0.0.1")
    serve.add_argument("--port", type=int, default=8000)
    serve.set_defaults(func=_serve)
    export = sub.add_parser("export-contracts", help="write openapi.json and mcp-tools.json")
    export.add_argument("--out", required=True)
    export.set_defaults(func=_export_contracts)
    demo = sub.add_parser("demo", help="rebuild .local from a tape and print visit cards")
    demo.add_argument("--tape", default="fixtures/tapes/synthetic-day")
    demo.add_argument("--serve", action="store_true", help="start the API afterwards")
    demo.add_argument("--host", default="127.0.0.1")
    demo.add_argument("--port", type=int, default=8000)
    demo.set_defaults(func=_demo)
    args = parser.parse_args(argv)
    args.func(args)
