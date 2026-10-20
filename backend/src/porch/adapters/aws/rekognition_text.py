"""Rekognition DetectText behind the LabelReader port.

Replaces Textract: the Free-plan SCP allows Rekognition in the home
region but not Textract. Returns LINE detections in reading order (Top
then Left of the bounding box), filtered by vision.ocr_min_confidence.
"""

import asyncio
import hashlib

from botocore.exceptions import BotoCoreError, ClientError
from pydantic import TypeAdapter
from types_boto3_rekognition import RekognitionClient
from types_boto3_rekognition.type_defs import TextDetectionTypeDef

from porch.adapters.cassette import Cassette, JsonValue
from porch.config import Settings
from porch.ports import LabelReader

from .clients import aws_port_error

_ADAPTER = "rekognition_detect_text"
_VERSION = 1
_DETECTIONS = TypeAdapter(list[TextDetectionTypeDef])


class RekognitionTextReader(LabelReader):
    def __init__(self, client: RekognitionClient, settings: Settings, cassette: Cassette) -> None:
        self._client = client
        self._cassette = cassette
        self._min_confidence = settings.vision.ocr_min_confidence
        self._sem = asyncio.Semaphore(settings.aws.rekognition_concurrency)

    async def read(self, image: bytes) -> tuple[str, ...]:
        request: dict[str, JsonValue] = {
            "image_sha256": hashlib.sha256(image).hexdigest(),
            "min_confidence": self._min_confidence,
        }
        detections = await self._cassette.call(
            _ADAPTER, _VERSION, request, lambda: self._read(image), _DETECTIONS
        )
        lines = [d for d in detections if self._is_line(d)]
        lines.sort(key=_line_position)
        return tuple(d.get("DetectedText", "") for d in lines)

    def _is_line(self, det: TextDetectionTypeDef) -> bool:
        return (
            det.get("Type") == "LINE"
            and float(det.get("Confidence", 0.0)) >= self._min_confidence
            and bool(det.get("DetectedText"))
        )

    async def _read(self, image: bytes) -> list[TextDetectionTypeDef]:
        async with self._sem:
            try:
                response = await asyncio.to_thread(self._client.detect_text, Image={"Bytes": image})
            except (ClientError, BotoCoreError) as exc:
                raise aws_port_error("rekognition", "detect_text", exc) from exc
            return list(response.get("TextDetections", []))


def _line_position(det: TextDetectionTypeDef) -> tuple[float, float]:
    box = det.get("Geometry", {}).get("BoundingBox", {})
    return (float(box.get("Top", 0.0)), float(box.get("Left", 0.0)))
