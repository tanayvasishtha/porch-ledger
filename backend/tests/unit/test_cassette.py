import asyncio
import hashlib
import json
from collections.abc import Mapping
from pathlib import Path

import pytest
from pydantic import TypeAdapter

from porch.adapters.cassette import (
    Cassette,
    CassetteCorruptError,
    CassetteMissError,
    JsonValue,
)

LIST_INT = TypeAdapter(list[int])
REQUEST: Mapping[str, JsonValue] = {"device": "d1", "ts": 123}


def test_record_then_replay_returns_same_and_never_calls_fn(tmp_path: Path) -> None:
    async def run() -> None:
        calls = 0

        async def fn() -> list[int]:
            nonlocal calls
            calls += 1
            return [1, 2, 3]

        result = await Cassette(tmp_path, "record").call("ring", 1, REQUEST, fn, LIST_INT)
        assert result == [1, 2, 3]
        assert calls == 1

        again = await Cassette(tmp_path, "replay").call("ring", 1, REQUEST, fn, LIST_INT)
        assert again == result
        assert calls == 1

    asyncio.run(run())


def test_record_writes_under_adapter_and_version(tmp_path: Path) -> None:
    async def run() -> None:
        async def fn() -> list[int]:
            return []

        await Cassette(tmp_path, "record").call("textract", 2, REQUEST, fn, LIST_INT)

    asyncio.run(run())
    files = list((tmp_path / "textract" / "v2").glob("*.json"))
    assert len(files) == 1


def test_replay_miss_names_adapter(tmp_path: Path) -> None:
    async def run() -> None:
        async def fn() -> list[int]:
            return [9]

        with pytest.raises(CassetteMissError) as excinfo:
            await Cassette(tmp_path, "replay").call("rekognition", 1, REQUEST, fn, LIST_INT)
        assert "rekognition" in str(excinfo.value)

    asyncio.run(run())


def test_live_writes_nothing(tmp_path: Path) -> None:
    async def run() -> None:
        async def fn() -> list[int]:
            return [4, 5]

        result = await Cassette(tmp_path, "live").call("ring", 1, REQUEST, fn, LIST_INT)
        assert result == [4, 5]

    asyncio.run(run())
    assert list(tmp_path.rglob("*")) == []


def test_bytes_roundtrip_writes_bin_and_replays(tmp_path: Path) -> None:
    payload = b"\x89PNG\r\n\x1a\nfake-image-bytes"

    async def run() -> None:
        called = False

        async def fn() -> bytes:
            nonlocal called
            called = True
            return payload

        stored = await Cassette(tmp_path, "record").call_bytes("s3", 1, REQUEST, fn)
        assert stored == payload
        assert called

        bins = list(tmp_path.rglob("*.bin"))
        assert len(bins) == 1
        assert bins[0].read_bytes() == payload
        envelope = json.loads(next(tmp_path.rglob("*.json")).read_text(encoding="utf-8"))
        assert envelope["body_file"] == bins[0].name

        called = False
        back = await Cassette(tmp_path, "replay").call_bytes("s3", 1, REQUEST, fn)
        assert back == payload
        assert not called

    asyncio.run(run())


def test_key_stable_across_key_order(tmp_path: Path) -> None:
    async def run() -> None:
        async def fn() -> list[int]:
            return [7]

        await Cassette(tmp_path, "record").call("ring", 1, {"a": 1, "b": 2}, fn, LIST_INT)
        reordered = {"b": 2, "a": 1}
        result = await Cassette(tmp_path, "replay").call("ring", 1, reordered, fn, LIST_INT)
        assert result == [7]

    asyncio.run(run())


def test_adapter_version_separates_cassettes(tmp_path: Path) -> None:
    async def run() -> None:
        async def fn() -> list[int]:
            return [1]

        await Cassette(tmp_path, "record").call("ring", 1, REQUEST, fn, LIST_INT)
        with pytest.raises(CassetteMissError):
            await Cassette(tmp_path, "replay").call("ring", 2, REQUEST, fn, LIST_INT)

    asyncio.run(run())


def test_envelope_missing_response_is_corrupt(tmp_path: Path) -> None:
    async def run() -> None:
        async def fn() -> list[int]:
            return [1]

        await Cassette(tmp_path, "record").call("ring", 1, REQUEST, fn, LIST_INT)
        env_path = next(tmp_path.rglob("*.json"))
        envelope = json.loads(env_path.read_text(encoding="utf-8"))
        del envelope["response"]
        env_path.write_text(json.dumps(envelope), encoding="utf-8")

        with pytest.raises(CassetteCorruptError):
            await Cassette(tmp_path, "replay").call("ring", 1, REQUEST, fn, LIST_INT)

    asyncio.run(run())


def test_non_dict_envelope_is_corrupt(tmp_path: Path) -> None:
    canonical = json.dumps(dict(REQUEST), sort_keys=True, separators=(",", ":"))
    key = hashlib.sha256(canonical.encode()).hexdigest()
    env_dir = tmp_path / "ring" / "v1"
    env_dir.mkdir(parents=True)
    (env_dir / f"{key}.json").write_text("[1, 2, 3]", encoding="utf-8")

    async def run() -> None:
        async def fn() -> list[int]:
            return [1]

        with pytest.raises(CassetteCorruptError):
            await Cassette(tmp_path, "replay").call("ring", 1, REQUEST, fn, LIST_INT)

    asyncio.run(run())


def test_missing_body_file_is_corrupt(tmp_path: Path) -> None:
    async def run() -> None:
        async def fn() -> bytes:
            return b"payload"

        await Cassette(tmp_path, "record").call_bytes("s3", 1, REQUEST, fn)
        bin_path = next(tmp_path.rglob("*.bin"))
        bin_path.unlink()

        with pytest.raises(CassetteCorruptError):
            await Cassette(tmp_path, "replay").call_bytes("s3", 1, REQUEST, fn)

    asyncio.run(run())
