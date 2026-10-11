"""SQLite Repository for local development and tests.

One connection per call, moved off the event loop with asyncio.to_thread.
WAL mode keeps readers unblocked while a write is in flight. Visits are
stored as codec-serialized JSON; id, house_id and start_ms columns exist
only for lookup and ordering.
"""

from __future__ import annotations

import asyncio
import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import replace
from pathlib import Path

from porch.adapters.codec import dumps_visit, loads_visit
from porch.domain import Visit

_SCHEMA = """
CREATE TABLE IF NOT EXISTS visits (
    id TEXT PRIMARY KEY,
    house_id TEXT NOT NULL,
    start_ms INTEGER NOT NULL,
    body TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_visits_house_start ON visits(house_id, start_ms);
CREATE TABLE IF NOT EXISTS houses (
    id TEXT PRIMARY KEY,
    version INTEGER NOT NULL
);
CREATE TABLE IF NOT EXISTS cursors (
    device_id TEXT PRIMARY KEY,
    ms INTEGER NOT NULL
);
"""

_BUMP_SQL = """
INSERT INTO houses (id, version) VALUES (?, 1)
ON CONFLICT(id) DO UPDATE SET version = version + 1
RETURNING version
"""


class SqliteRepository:
    def __init__(self, path: Path) -> None:
        self._path = path

    async def save_visits(self, visits: list[Visit]) -> None:
        await asyncio.to_thread(self._save_visits, visits)

    async def visits_between(self, house_id: str, start_ms: int, end_ms: int) -> list[Visit]:
        return await asyncio.to_thread(self._visits_between, house_id, start_ms, end_ms)

    async def get_visit(self, visit_id: str) -> Visit | None:
        return await asyncio.to_thread(self._get_visit, visit_id)

    async def claim(self, visit_id: str, resident_id: str) -> Visit | None:
        return await asyncio.to_thread(self._claim, visit_id, resident_id)

    async def house_version(self, house_id: str) -> int:
        return await asyncio.to_thread(self._house_version, house_id)

    async def bump_version(self, house_id: str) -> int:
        return await asyncio.to_thread(self._bump_version, house_id)

    async def get_cursor(self, device_id: str) -> int | None:
        return await asyncio.to_thread(self._get_cursor, device_id)

    async def set_cursor(self, device_id: str, ms: int) -> None:
        await asyncio.to_thread(self._set_cursor, device_id, ms)

    def _connect(self) -> sqlite3.Connection:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(self._path)
        conn.execute("PRAGMA journal_mode=WAL")
        conn.executescript(_SCHEMA)
        return conn

    @contextmanager
    def _conn(self) -> Iterator[sqlite3.Connection]:
        conn = self._connect()
        try:
            with conn:
                yield conn
        finally:
            conn.close()

    @staticmethod
    def _bump(conn: sqlite3.Connection, house_id: str) -> int:
        row = conn.execute(_BUMP_SQL, (house_id,)).fetchone()
        assert row is not None
        return int(row[0])

    def _save_visits(self, visits: list[Visit]) -> None:
        changed_houses: set[str] = set()
        with self._conn() as conn:
            for visit in visits:
                row = conn.execute("SELECT body FROM visits WHERE id = ?", (visit.id,)).fetchone()
                merged = visit
                if row is not None:
                    stored = loads_visit(row[0])
                    merged = replace(
                        visit,
                        claimed_by=visit.claimed_by or stored.claimed_by,
                        version=stored.version,
                    )
                    if merged == stored:
                        continue
                    merged = replace(merged, version=stored.version + 1)
                conn.execute(
                    "INSERT OR REPLACE INTO visits (id, house_id, start_ms, body)"
                    " VALUES (?, ?, ?, ?)",
                    (merged.id, merged.house_id, merged.start_ms, dumps_visit(merged)),
                )
                changed_houses.add(merged.house_id)
            for house_id in changed_houses:
                self._bump(conn, house_id)

    def _visits_between(self, house_id: str, start_ms: int, end_ms: int) -> list[Visit]:
        with self._conn() as conn:
            rows = conn.execute(
                "SELECT body FROM visits WHERE house_id = ?"
                " AND start_ms >= ? AND start_ms < ? ORDER BY start_ms, id",
                (house_id, start_ms, end_ms),
            )
            return [loads_visit(row[0]) for row in rows]

    def _get_visit(self, visit_id: str) -> Visit | None:
        with self._conn() as conn:
            row = conn.execute("SELECT body FROM visits WHERE id = ?", (visit_id,)).fetchone()
            return loads_visit(row[0]) if row is not None else None

    def _claim(self, visit_id: str, resident_id: str) -> Visit | None:
        with self._conn() as conn:
            row = conn.execute("SELECT body FROM visits WHERE id = ?", (visit_id,)).fetchone()
            if row is None:
                return None
            stored = loads_visit(row[0])
            updated = replace(stored, claimed_by=resident_id, version=stored.version + 1)
            conn.execute(
                "UPDATE visits SET body = ? WHERE id = ?",
                (dumps_visit(updated), visit_id),
            )
            self._bump(conn, stored.house_id)
            return updated

    def _house_version(self, house_id: str) -> int:
        with self._conn() as conn:
            row = conn.execute("SELECT version FROM houses WHERE id = ?", (house_id,)).fetchone()
            return int(row[0]) if row is not None else 0

    def _bump_version(self, house_id: str) -> int:
        with self._conn() as conn:
            return self._bump(conn, house_id)

    def _get_cursor(self, device_id: str) -> int | None:
        with self._conn() as conn:
            row = conn.execute(
                "SELECT ms FROM cursors WHERE device_id = ?", (device_id,)
            ).fetchone()
            return int(row[0]) if row is not None else None

    def _set_cursor(self, device_id: str, ms: int) -> None:
        with self._conn() as conn:
            conn.execute(
                "INSERT OR REPLACE INTO cursors (device_id, ms) VALUES (?, ?)",
                (device_id, ms),
            )
