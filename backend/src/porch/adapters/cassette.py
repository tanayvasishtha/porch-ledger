"""Record/replay cassette for adapter calls.

`live` calls the wrapped function and keeps nothing. `record` calls it
and writes a JSON envelope under `root/<adapter>/v<version>/<sha>.json`;
binary payloads go to a sibling `<sha>.bin` written first, so a crash
never leaves a JSON envelope pointing at a missing body file. `replay`
reads the envelope back and never calls the wrapped function.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Awaitable, Callable, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Literal, TypeVar

from pydantic import TypeAdapter

T = TypeVar("T")
type JsonValue = bool | int | float | str | list[JsonValue] | dict[str, JsonValue] | None

REQUEST_PREVIEW_CHARS = 200


@dataclass(frozen=True, slots=True)
class _CallSpec:
    adapter: str
    version: int
    request: Mapping[str, JsonValue]


class CassetteMissError(Exception):
    """Replay found no recorded response for a request."""

    def __init__(self, adapter: str, key: str, canonical_request: str) -> None:
        self.adapter = adapter
        self.key = key
        super().__init__(
            f"cassette miss: adapter={adapter} key={key} "
            f"request={canonical_request[:REQUEST_PREVIEW_CHARS]}"
        )


class CassetteCorruptError(Exception):
    """A cassette file exists but is malformed or incomplete."""

    def __init__(self, adapter: str, path: Path) -> None:
        self.adapter = adapter
        self.path = path
        super().__init__(f"cassette corrupt: adapter={adapter} path={path}")


class Cassette:
    def __init__(self, root: Path, mode: Literal["live", "record", "replay"]) -> None:
        self.root = root
        self.mode = mode

    async def call(
        self,
        adapter: str,
        version: int,
        request: Mapping[str, JsonValue],
        fn: Callable[[], Awaitable[T]],
        codec: TypeAdapter[T],
    ) -> T:
        """Call fn in live/record, or replay the recorded response."""

        def encode(result: T, _path: Path) -> JsonValue:
            return {"response": codec.dump_python(result, mode="json")}

        def decode(envelope: JsonValue, path: Path) -> T:
            if not isinstance(envelope, dict) or "response" not in envelope:
                raise CassetteCorruptError(adapter, path)
            return codec.validate_python(envelope["response"])

        spec = _CallSpec(adapter, version, request)
        return await self._call(spec, fn, encode, decode)

    async def call_bytes(
        self,
        adapter: str,
        version: int,
        request: Mapping[str, JsonValue],
        fn: Callable[[], Awaitable[bytes]],
    ) -> bytes:
        """Same as call for binary payloads, stored as a sibling .bin file."""

        def encode(data: bytes, path: Path) -> JsonValue:
            bin_path = path.with_suffix(".bin")
            self._write_bytes(bin_path, data)
            return {"body_file": bin_path.name}

        def decode(envelope: JsonValue, path: Path) -> bytes:
            if not isinstance(envelope, dict):
                raise CassetteCorruptError(adapter, path)
            body_file = envelope.get("body_file")
            if not isinstance(body_file, str):
                raise CassetteCorruptError(adapter, path)
            bin_path = path.parent / body_file
            if not bin_path.is_file():
                raise CassetteCorruptError(adapter, path)
            return bin_path.read_bytes()

        spec = _CallSpec(adapter, version, request)
        return await self._call(spec, fn, encode, decode)

    async def _call(
        self,
        spec: _CallSpec,
        fn: Callable[[], Awaitable[T]],
        encode: Callable[[T, Path], JsonValue],
        decode: Callable[[JsonValue, Path], T],
    ) -> T:
        if self.mode == "live":
            return await fn()
        canonical = self._canonical(spec.request)
        path = self._path(spec.adapter, spec.version, canonical)
        if self.mode == "record":
            result = await fn()
            path.parent.mkdir(parents=True, exist_ok=True)
            extra = encode(result, path)
            if not isinstance(extra, dict):
                raise TypeError(type(extra))
            self._write(path, {"request": dict(spec.request), **extra})
            return result
        loaded = self._read(path, spec.adapter, canonical)
        return decode(loaded, path)

    @staticmethod
    def _canonical(request: Mapping[str, JsonValue]) -> str:
        return json.dumps(dict(request), sort_keys=True, separators=(",", ":"))

    def _path(self, adapter: str, version: int, canonical: str) -> Path:
        key = hashlib.sha256(canonical.encode()).hexdigest()
        return self.root / adapter / f"v{version}" / f"{key}.json"

    @staticmethod
    def _write(path: Path, envelope: dict[str, JsonValue]) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(path.suffix + ".tmp")
        tmp.write_text(json.dumps(envelope), encoding="utf-8")
        tmp.replace(path)

    @staticmethod
    def _write_bytes(path: Path, data: bytes) -> None:
        tmp = path.with_suffix(path.suffix + ".tmp")
        tmp.write_bytes(data)
        tmp.replace(path)

    @staticmethod
    def _read(path: Path, adapter: str, canonical: str) -> JsonValue:
        if not path.is_file():
            raise CassetteMissError(adapter, path.stem, canonical)
        loaded: JsonValue = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(loaded, dict):
            raise CassetteCorruptError(adapter, path)
        return loaded
