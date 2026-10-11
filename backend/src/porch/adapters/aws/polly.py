"""Polly SynthesizeSpeech behind the Speech port.

The cassette stores the mp3 bytes; the media store put() happens outside
the cassette so replay still lands the audio in whatever store is active.
Identical text+voice pairs memoise to the same media key in-process.
"""

import asyncio
import hashlib
from typing import cast

from botocore.exceptions import BotoCoreError, ClientError
from types_boto3_polly import PollyClient
from types_boto3_polly.literals import EngineType, OutputFormatType, VoiceIdType

from porch.adapters.cassette import Cassette, JsonValue
from porch.config import Settings
from porch.ports import MediaStore, Speech

from .clients import aws_port_error

_ADAPTER = "polly_synthesize"
_VERSION = 1
_FORMAT: OutputFormatType = "mp3"
_SUFFIX = ".mp3"


class PollySpeech(Speech):
    def __init__(
        self,
        client: PollyClient,
        settings: Settings,
        cassette: Cassette,
        media: MediaStore,
    ) -> None:
        self._client = client
        self._cassette = cassette
        self._media = media
        self._voice = cast(VoiceIdType, settings.aws.polly_voice)
        self._engine: EngineType = settings.aws.polly_engine
        self._sem = asyncio.Semaphore(settings.aws.polly_concurrency)
        self._memo: dict[tuple[str, str], str] = {}

    async def synthesize(self, text: str) -> str:
        memo_key = (text, self._voice)
        if memo_key in self._memo:
            return self._memo[memo_key]
        request: dict[str, JsonValue] = {
            "text_sha256": hashlib.sha256(text.encode()).hexdigest(),
            "voice": self._voice,
            "engine": self._engine,
            "format": _FORMAT,
        }
        audio = await self._cassette.call_bytes(
            _ADAPTER, _VERSION, request, lambda: self._synthesize(text)
        )
        key = await self._media.put(audio, _SUFFIX)
        self._memo[memo_key] = key
        return key

    async def _synthesize(self, text: str) -> bytes:
        async with self._sem:
            try:
                response = await asyncio.to_thread(
                    self._client.synthesize_speech,
                    OutputFormat=_FORMAT,
                    Text=text,
                    VoiceId=self._voice,
                    Engine=self._engine,
                )
                body: bytes = await asyncio.to_thread(response["AudioStream"].read)
            except (ClientError, BotoCoreError) as exc:
                raise aws_port_error("polly", "synthesize_speech", exc) from exc
            return body
