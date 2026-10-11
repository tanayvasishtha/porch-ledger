"""S3 MediaStore: content-addressed keys in the media bucket.

put() is head_object + conditional put_object, so re-uploading existing
bytes costs one HEAD and no body. get() and url() go through the cassette
like every other adapter call.
"""

import asyncio
import hashlib
import mimetypes

from botocore.exceptions import BotoCoreError, ClientError
from pydantic import TypeAdapter
from types_boto3_s3 import S3Client

from porch.adapters.cassette import Cassette, JsonValue
from porch.config import Settings
from porch.ports import MediaStore

from .clients import aws_port_error

_ADAPTER = "s3_media"
_VERSION = 1
_STR = TypeAdapter(str)

_NOT_FOUND = frozenset({"404", "NoSuchKey", "NotFound"})


class S3MediaStore(MediaStore):
    def __init__(self, client: S3Client, settings: Settings, cassette: Cassette) -> None:
        self._client = client
        self._bucket = settings.aws.media_bucket
        self._cassette = cassette
        self._sem = asyncio.Semaphore(settings.aws.s3_concurrency)

    def s3_uri(self, key: str) -> str:
        return f"s3://{self._bucket}/{key}"

    async def put(self, data: bytes, suffix: str) -> str:
        key = hashlib.sha256(data).hexdigest() + suffix
        content_type = mimetypes.guess_type(f"file{suffix}")[0] or "application/octet-stream"
        request: dict[str, JsonValue] = {
            "key": key,
            "bytes": len(data),
            "content_type": content_type,
        }
        return await self._cassette.call(
            _ADAPTER,
            _VERSION,
            request,
            lambda: self._put(data, key, content_type),
            _STR,
        )

    async def get(self, key: str) -> bytes:
        return await self._cassette.call_bytes(
            _ADAPTER, _VERSION, {"op": "get", "key": key}, lambda: self._get(key)
        )

    async def url(self, key: str, ttl_s: int) -> str:
        return await self._cassette.call(
            _ADAPTER,
            _VERSION,
            {"op": "url", "key": key, "ttl_s": ttl_s},
            lambda: self._url(key, ttl_s),
            _STR,
        )

    async def _put(self, data: bytes, key: str, content_type: str) -> str:
        async with self._sem:
            if await self._exists(key):
                return key
            try:
                await asyncio.to_thread(
                    self._client.put_object,
                    Bucket=self._bucket,
                    Key=key,
                    Body=data,
                    ContentType=content_type,
                )
            except (ClientError, BotoCoreError) as exc:
                raise aws_port_error("s3", "put_object", exc) from exc
            return key

    async def _exists(self, key: str) -> bool:
        try:
            await asyncio.to_thread(self._client.head_object, Bucket=self._bucket, Key=key)
        except ClientError as exc:
            code = exc.response.get("Error", {}).get("Code", "")
            if code in _NOT_FOUND:
                return False
            raise aws_port_error("s3", "head_object", exc) from exc
        except BotoCoreError as exc:
            raise aws_port_error("s3", "head_object", exc) from exc
        return True

    async def _get(self, key: str) -> bytes:
        async with self._sem:
            try:
                obj = await asyncio.to_thread(self._client.get_object, Bucket=self._bucket, Key=key)
                body: bytes = await asyncio.to_thread(obj["Body"].read)
            except (ClientError, BotoCoreError) as exc:
                raise aws_port_error("s3", "get_object", exc) from exc
            return body

    async def _url(self, key: str, ttl_s: int) -> str:
        try:
            return await asyncio.to_thread(
                self._client.generate_presigned_url,
                "get_object",
                Params={"Bucket": self._bucket, "Key": key},
                ExpiresIn=ttl_s,
            )
        except (ClientError, BotoCoreError) as exc:
            raise aws_port_error("s3", "generate_presigned_url", exc) from exc
