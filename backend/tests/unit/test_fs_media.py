import asyncio
import hashlib
from pathlib import Path

import pytest

from porch.adapters.local import FileMediaStore, MediaKeyError

DATA = b"fake-png-bytes"


def test_put_get_url(tmp_path: Path) -> None:
    async def run() -> None:
        store = FileMediaStore(tmp_path, "http://localhost:9000")
        key = await store.put(DATA, ".png")
        assert key == hashlib.sha256(DATA).hexdigest() + ".png"
        assert (tmp_path / key).read_bytes() == DATA
        assert await store.get(key) == DATA
        assert await store.url(key, 60) == f"http://localhost:9000/v1/media/{key}"

    asyncio.run(run())


def test_put_idempotent(tmp_path: Path) -> None:
    async def run() -> None:
        store = FileMediaStore(tmp_path, "http://localhost:9000")
        key1 = await store.put(DATA, ".png")
        first_mtime = (tmp_path / key1).stat().st_mtime_ns
        key2 = await store.put(DATA, ".png")
        assert key1 == key2
        assert (tmp_path / key1).stat().st_mtime_ns == first_mtime
        assert [p for p in tmp_path.iterdir() if not p.name.endswith(".tmp")] == [tmp_path / key1]

    asyncio.run(run())


@pytest.mark.parametrize("key", ["../escape", "a/b", "a\\b", "x..y", ""])
def test_unsafe_keys_rejected(tmp_path: Path, key: str) -> None:
    async def run() -> None:
        store = FileMediaStore(tmp_path, "http://localhost:9000")
        with pytest.raises(MediaKeyError):
            await store.get(key)
        with pytest.raises(MediaKeyError):
            await store.url(key, 60)

    asyncio.run(run())
