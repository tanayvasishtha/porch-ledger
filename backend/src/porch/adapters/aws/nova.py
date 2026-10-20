"""Bedrock Nova clip description behind the ClipDescriber port.

The clip bytes go inline in the Converse request (2-6 MB, under the
inline limit): Bedrock in us-east-1 cannot read S3 in the home region.
The response is parsed defensively: code fences stripped, JSON
validated, accusations and overlong or uncertain summaries dropped to
None so enrich keeps its fallback copy. The cassette request still keys
on the clip's S3 URI so recorded runs replay unchanged.
"""

import asyncio
import re
from typing import cast

from botocore.exceptions import BotoCoreError, ClientError
from pydantic import BaseModel, ConfigDict, TypeAdapter, ValidationError
from types_boto3_bedrock_runtime import BedrockRuntimeClient
from types_boto3_bedrock_runtime.literals import VideoFormatType

from porch.adapters.aws.s3_media import S3MediaStore
from porch.adapters.cassette import Cassette, JsonValue
from porch.config import Settings
from porch.ports import ClipDescriber, PortError

from .clients import aws_port_error

_ADAPTER = "nova_converse"
_VERSION = 1
_STR = TypeAdapter(str)

# Never accuse in card copy; the same list guards model output.
ACCUSATION_WORDS = frozenset({"stolen", "theft", "thief", "suspicious", "intruder"})
_ACCUSATION_RE = re.compile(r"\b(" + "|".join(sorted(ACCUSATION_WORDS)) + r")\b", re.IGNORECASE)

_FORMATS = frozenset({"mp4", "mov", "mkv", "webm", "flv", "mpg", "mpeg", "wmv", "3gp"})

_PROMPT = (
    "Describe what happens at this front door in one plain present-tense "
    "sentence covering the whole clip: arrivals, anything left or taken, "
    "and departures. Do not guess anyone's identity and do not use names. "
    'Answer only with JSON: {"summary": "...", "uncertain": true|false}. '
    "Set uncertain true when you cannot tell what happened."
)


class _Summary(BaseModel):
    model_config = ConfigDict(strict=True)

    summary: str
    uncertain: bool


class NovaDescriber(ClipDescriber):
    def __init__(
        self,
        client: BedrockRuntimeClient,
        media: S3MediaStore,
        settings: Settings,
        cassette: Cassette,
    ) -> None:
        self._client = client
        self._media = media
        self._cassette = cassette
        self._model_id = settings.vision.describe_model_id
        self._max_tokens = settings.vision.describe_max_tokens
        self._max_chars = settings.vision.describe_max_chars
        self._sem = asyncio.Semaphore(settings.aws.bedrock_concurrency)

    async def describe(self, clip_key: str) -> str | None:
        video_format = self._video_format(clip_key)
        uri = self._media.s3_uri(clip_key)
        request: dict[str, JsonValue] = {
            "clip_uri": uri,
            "video_format": video_format,
            "model_id": self._model_id,
            "max_tokens": self._max_tokens,
            "temperature": 0.0,
        }
        text = await self._cassette.call(
            _ADAPTER,
            _VERSION,
            request,
            lambda: self._converse(clip_key, video_format),
            _STR,
        )
        return self._parse(text)

    async def _converse(self, clip_key: str, video_format: VideoFormatType) -> str:
        data = await self._media.get(clip_key)
        async with self._sem:
            try:
                response = await asyncio.to_thread(
                    self._client.converse,
                    modelId=self._model_id,
                    messages=[
                        {
                            "role": "user",
                            "content": [
                                {
                                    "video": {
                                        "format": video_format,
                                        "source": {"bytes": data},
                                    }
                                },
                                {"text": _PROMPT},
                            ],
                        }
                    ],
                    inferenceConfig={
                        "maxTokens": self._max_tokens,
                        "temperature": 0.0,
                    },
                )
            except (ClientError, BotoCoreError) as exc:
                raise aws_port_error("bedrock", "converse", exc) from exc
            blocks = response.get("output", {}).get("message", {}).get("content", [])
            return "\n".join(
                block.get("text", "")
                for block in blocks
                if isinstance(block, dict) and block.get("text")
            )

    def _parse(self, text: str) -> str | None:
        cleaned = text.strip()
        if cleaned.startswith("```"):
            cleaned = re.sub(r"^```[a-zA-Z]*\n?|\n?```$", "", cleaned).strip()
        try:
            payload = _Summary.model_validate_json(cleaned)
        except ValidationError:
            return None
        summary = payload.summary.strip()
        if payload.uncertain or not summary:
            return None
        if len(summary) > self._max_chars:
            return None
        if _ACCUSATION_RE.search(summary):
            return None
        return summary

    @staticmethod
    def _video_format(clip_key: str) -> VideoFormatType:
        suffix = clip_key.rsplit(".", 1)[-1].lower()
        if suffix not in _FORMATS:
            msg = f"nova.converse: unknown clip format for {clip_key}"
            raise PortError(msg)
        return cast(VideoFormatType, suffix)
