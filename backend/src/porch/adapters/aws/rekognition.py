"""Rekognition DetectLabels behind the Labeler port.

Image bytes never enter the cassette request; only their sha256 plus the
label parameters do. Labels pass through vision.label_map so cassette
replays and tests see the same mapped detections.
"""

import asyncio
import hashlib

from botocore.exceptions import BotoCoreError, ClientError
from pydantic import TypeAdapter
from types_boto3_rekognition import RekognitionClient
from types_boto3_rekognition.type_defs import (
    BoundingBoxTypeDef,
    LabelTypeDef,
)

from porch.adapters.cassette import Cassette, JsonValue
from porch.config import Settings
from porch.domain import Detection, NormBox
from porch.ports import Labeler

from .clients import aws_port_error

_ADAPTER = "rekognition_detect"
_VERSION = 1
_LABELS = TypeAdapter(list[LabelTypeDef])


class RekognitionLabeler(Labeler):
    def __init__(self, client: RekognitionClient, settings: Settings, cassette: Cassette) -> None:
        self._client = client
        self._cassette = cassette
        self._label_map = settings.vision.label_map
        self._max_labels = settings.vision.rekognition_max_labels
        self._min_confidence = settings.vision.rekognition_min_confidence
        self._sem = asyncio.Semaphore(settings.aws.rekognition_concurrency)

    async def detect(self, image: bytes) -> tuple[Detection, ...]:
        request: dict[str, JsonValue] = {
            "image_sha256": hashlib.sha256(image).hexdigest(),
            "max_labels": self._max_labels,
            "min_confidence": self._min_confidence,
        }
        labels = await self._cassette.call(
            _ADAPTER, _VERSION, request, lambda: self._detect(image), _LABELS
        )
        return tuple(detection for label in labels for detection in self._detections(label))

    async def _detect(self, image: bytes) -> list[LabelTypeDef]:
        async with self._sem:
            try:
                response = await asyncio.to_thread(
                    self._client.detect_labels,
                    Image={"Bytes": image},
                    MaxLabels=self._max_labels,
                    MinConfidence=self._min_confidence,
                )
            except (ClientError, BotoCoreError) as exc:
                raise aws_port_error("rekognition", "detect_labels", exc) from exc
            return list(response.get("Labels", []))

    def _detections(self, label: LabelTypeDef) -> list[Detection]:
        mapped = self._label_map.get(label.get("Name", ""))
        if mapped is None:
            return []
        confidence = float(label.get("Confidence", 0.0)) / 100.0
        instances = label.get("Instances") or []
        if not instances:
            return [Detection(label=mapped, confidence=confidence, box=None)]
        detections: list[Detection] = []
        for instance in instances:
            box = _norm_box(instance.get("BoundingBox", {}))
            if box is None:
                continue
            instance_conf = float(instance.get("Confidence", label.get("Confidence", 0.0)))
            detections.append(Detection(label=mapped, confidence=instance_conf / 100.0, box=box))
        return detections


def _norm_box(bounding: BoundingBoxTypeDef) -> NormBox | None:
    x = _clamp01(float(bounding.get("Left", 0.0)))
    y = _clamp01(float(bounding.get("Top", 0.0)))
    width = min(max(float(bounding.get("Width", 0.0)), 0.0), 1.0 - x)
    height = min(max(float(bounding.get("Height", 0.0)), 0.0), 1.0 - y)
    if width <= 0.0 or height <= 0.0:
        return None
    return NormBox(x=x, y=y, w=width, h=height)


def _clamp01(value: float) -> float:
    return min(max(value, 0.0), 1.0)
