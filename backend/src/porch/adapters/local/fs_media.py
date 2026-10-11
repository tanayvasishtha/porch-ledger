"""Local filesystem MediaStore for dev and tests.

Files land at root/<sha256><suffix> written atomically; url() only joins
public_base_url with the key, so the ttl_s argument is accepted for
protocol parity and ignored locally.
"""

import asyncio
import hashlib
from pathlib import Path

from porch.ports import PortError

_SEPARATORS = ("/", "\\")
_PARENT_REF = ".."


class MediaKeyError(Exception):
    """Media key that would escape the store root."""

    def __init__(self, key: str) -> None:
        super().__init__(f"unsafe media key: {key}")


def _check_key(key: str) -> None:
    if not key or any(sep in key for sep in _SEPARATORS) or _PARENT_REF in key:
        raise MediaKeyError(key)


class FileMediaStore:
    def __init__(self, root: Path, public_base_url: str) -> None:
        self._root = root
        self._base_url = public_base_url.rstrip("/")

    async def put(self, data: bytes, suffix: str) -> str:
        return await asyncio.to_thread(self._put, data, suffix)

    async def get(self, key: str) -> bytes:
        return await asyncio.to_thread(self._get, key)

    async def url(self, key: str, ttl_s: int) -> str:
        del ttl_s
        _check_key(key)
        return f"{self._base_url}/v1/media/{key}"

    def _put(self, data: bytes, suffix: str) -> str:
        self._root.mkdir(parents=True, exist_ok=True)
        key = hashlib.sha256(data).hexdigest() + suffix
        path = self._root / key
        if not path.exists():
            tmp = path.with_name(f"{path.name}.tmp")
            tmp.write_bytes(data)
            tmp.replace(path)
        return key

    def _get(self, key: str) -> bytes:
        _check_key(key)
        try:
            return (self._root / key).read_bytes()
        except FileNotFoundError as exc:
            msg = f"media not found: {key}"
            raise PortError(msg) from exc
