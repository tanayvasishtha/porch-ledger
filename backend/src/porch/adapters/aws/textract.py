"""Textract DetectDocumentText behind the LabelReader port.

Returns LINE block texts in reading order (Top then Left of the line
bounding box), filtered by vision.ocr_min_confidence.
"""

import asyncio
import hashlib

from botocore.exceptions import BotoCoreError, ClientError
from pydantic import TypeAdapter
from types_boto3_textract import TextractClient
from types_boto3_textract.type_defs import BlockTypeDef

from porch.adapters.cassette import Cassette, JsonValue
from porch.config import Settings
from porch.ports import LabelReader

from .clients import aws_port_error

_ADAPTER = "textract_detect"
_VERSION = 1
_BLOCKS = TypeAdapter(list[BlockTypeDef])


class TextractReader(LabelReader):
    def __init__(self, client: TextractClient, settings: Settings, cassette: Cassette) -> None:
        self._client = client
        self._cassette = cassette
        self._min_confidence = settings.vision.ocr_min_confidence
        self._sem = asyncio.Semaphore(settings.aws.textract_concurrency)

    async def read(self, image: bytes) -> tuple[str, ...]:
        request: dict[str, JsonValue] = {
            "image_sha256": hashlib.sha256(image).hexdigest(),
            "min_confidence": self._min_confidence,
        }
        blocks = await self._cassette.call(
            _ADAPTER, _VERSION, request, lambda: self._read(image), _BLOCKS
        )
        lines = [block for block in blocks if self._is_line(block)]
        lines.sort(key=_line_position)
        return tuple(block.get("Text", "") for block in lines)

    def _is_line(self, block: BlockTypeDef) -> bool:
        return (
            block.get("BlockType") == "LINE"
            and float(block.get("Confidence", 0.0)) >= self._min_confidence
            and bool(block.get("Text"))
        )

    async def _read(self, image: bytes) -> list[BlockTypeDef]:
        async with self._sem:
            try:
                response = await asyncio.to_thread(
                    self._client.detect_document_text, Document={"Bytes": image}
                )
            except (ClientError, BotoCoreError) as exc:
                raise aws_port_error("textract", "detect_document_text", exc) from exc
            return list(response.get("Blocks", []))


def _line_position(block: BlockTypeDef) -> tuple[float, float]:
    box = block.get("Geometry", {}).get("BoundingBox", {})
    return (float(box.get("Top", 0.0)), float(box.get("Left", 0.0)))
