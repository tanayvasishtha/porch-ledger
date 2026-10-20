"""AWS adapter tests: Stubber-backed clients, record/replay, PortError."""

import asyncio
import hashlib
import io
import re
from pathlib import Path
from typing import Any

import boto3
import pytest
from botocore.exceptions import BotoCoreError
from botocore.response import StreamingBody
from botocore.stub import Stubber

from porch.adapters.aws import (
    PollySpeech,
    RekognitionLabeler,
    RekognitionTextReader,
    S3MediaStore,
    build_clients,
)
from porch.adapters.aws.clients import aws_port_error
from porch.adapters.cassette import Cassette
from porch.adapters.local import FileMediaStore
from porch.config import AwsSettings, Settings
from porch.domain import NormBox
from porch.ports import PortError


def _client(name: str) -> Any:
    # boto3-stubs overloads on literal service names; tests keep it dynamic.
    return boto3.Session(
        region_name="us-east-1",
        aws_access_key_id="test",
        aws_secret_access_key="test",
    ).client(name)  # type: ignore[call-overload]


def _settings(**aws: Any) -> Settings:
    return Settings(aws=AwsSettings(media_bucket="porch-media", **aws))


def test_build_clients_sets_region_and_port_error_names_core_error() -> None:
    clients = build_clients(_settings())
    assert clients.s3.meta.region_name == "us-east-1"
    err = aws_port_error("s3", "get_object", BotoCoreError())
    assert str(err) == "s3.get_object: BotoCoreError"


# --- S3MediaStore ---------------------------------------------------------


def test_s3_put_uploads_once_and_skips_existing(tmp_path: Path) -> None:
    client = _client("s3")
    settings = _settings()
    store = S3MediaStore(client, settings, Cassette(tmp_path, "live"))
    data = b"frame-bytes"
    key = hashlib.sha256(data).hexdigest() + ".jpg"

    with Stubber(client) as stubber:
        stubber.add_client_error("head_object", "404")
        stubber.add_response(
            "put_object",
            {},
            {
                "Bucket": "porch-media",
                "Key": key,
                "Body": data,
                "ContentType": "image/jpeg",
            },
        )
        assert asyncio.run(store.put(data, ".jpg")) == key

    with Stubber(client) as stubber:
        stubber.add_response("head_object", {"ETag": '"x"'}, {"Bucket": "porch-media", "Key": key})
        assert asyncio.run(store.put(data, ".jpg")) == key
        # Only head_object was queued; a put_object call would raise.
        stubber.assert_no_pending_responses()


def test_s3_get_and_url(tmp_path: Path) -> None:
    client = _client("s3")
    store = S3MediaStore(client, _settings(), Cassette(tmp_path, "live"))
    key = "abc123.jpg"
    body = StreamingBody(io.BytesIO(b"image-data"), len("image-data"))

    with Stubber(client) as stubber:
        stubber.add_response("get_object", {"Body": body}, {"Bucket": "porch-media", "Key": key})
        assert asyncio.run(store.get(key)) == b"image-data"
        stubber.assert_no_pending_responses()

    url = asyncio.run(store.url(key, ttl_s=600))
    assert url.startswith("https://porch-media") and key in url and "Expires=" in url
    assert store.s3_uri(key) == "s3://porch-media/abc123.jpg"


def test_s3_client_error_is_port_error(tmp_path: Path) -> None:
    client = _client("s3")
    store = S3MediaStore(client, _settings(), Cassette(tmp_path, "live"))
    with Stubber(client) as stubber:
        stubber.add_client_error("get_object", "AccessDenied")
        with pytest.raises(PortError, match=re.escape("s3.get_object")):
            asyncio.run(store.get("x.jpg"))


# --- RekognitionLabeler -----------------------------------------------------


_REKOGNITION_RESPONSE = {
    "Labels": [
        {
            "Name": "Package",
            "Confidence": 95.0,
            "Instances": [
                {
                    "BoundingBox": {"Left": 0.1, "Top": 0.2, "Width": 0.3, "Height": 0.4},
                    "Confidence": 90.0,
                }
            ],
        },
        {
            "Name": "Car",
            "Confidence": 80.0,
            "Instances": [{"BoundingBox": {"Left": 0.9, "Top": 0.1, "Width": 0.5, "Height": 0.3}}],
        },
        {"Name": "Person", "Confidence": 70.0, "Instances": []},
        {
            "Name": "Zebra",
            "Confidence": 99.0,
            "Instances": [{"BoundingBox": {"Left": 0.1, "Top": 0.1, "Width": 0.1, "Height": 0.1}}],
        },
        {
            "Name": "Box",
            "Confidence": 60.0,
            "Instances": [{"BoundingBox": {"Left": 1.0, "Top": 0.5, "Width": 0.5, "Height": 0.5}}],
        },
    ]
}


def test_rekognition_maps_clamps_and_filters(tmp_path: Path) -> None:
    client = _client("rekognition")
    labeler = RekognitionLabeler(client, _settings(), Cassette(tmp_path, "live"))
    image = b"jpeg-bytes"

    with Stubber(client) as stubber:
        stubber.add_response(
            "detect_labels",
            _REKOGNITION_RESPONSE,
            {"Image": {"Bytes": image}, "MaxLabels": 25, "MinConfidence": 60.0},
        )
        detections = asyncio.run(labeler.detect(image))

    assert [d.label for d in detections] == ["box", "vehicle", "person"]
    box, vehicle, person = detections
    assert box.confidence == pytest.approx(0.9) and box.box == NormBox(0.1, 0.2, 0.3, 0.4)
    assert vehicle.confidence == pytest.approx(0.8)
    assert vehicle.box is not None
    assert vehicle.box.x == pytest.approx(0.9)
    assert vehicle.box.w == pytest.approx(0.1)  # clamped into the unit square
    assert person.box is None and person.confidence == pytest.approx(0.7)


def test_rekognition_client_error_is_port_error(tmp_path: Path) -> None:
    client = _client("rekognition")
    labeler = RekognitionLabeler(client, _settings(), Cassette(tmp_path, "live"))
    with Stubber(client) as stubber:
        stubber.add_client_error("detect_labels", "ProvisionedThroughputExceededException")
        with pytest.raises(PortError, match=re.escape("rekognition.detect_labels")):
            asyncio.run(labeler.detect(b"img"))


def test_rekognition_record_then_replay_skips_client(tmp_path: Path) -> None:
    client = _client("rekognition")
    image = b"img"
    stubber = Stubber(client)
    stubber.activate()
    stubber.add_response(
        "detect_labels",
        _REKOGNITION_RESPONSE,
        {"Image": {"Bytes": image}, "MaxLabels": 25, "MinConfidence": 60.0},
    )
    recorded = asyncio.run(
        RekognitionLabeler(client, _settings(), Cassette(tmp_path, "record")).detect(image)
    )
    # Replaying hits the cassette; the stubber has no queued responses left.
    replayed = asyncio.run(
        RekognitionLabeler(client, _settings(), Cassette(tmp_path, "replay")).detect(image)
    )
    stubber.deactivate()
    assert replayed == recorded


# --- RekognitionTextReader --------------------------------------------------


def _line(text: str, top: float, left: float, confidence: float = 95.0) -> dict[str, Any]:
    return {
        "Type": "LINE",
        "DetectedText": text,
        "Confidence": confidence,
        "Geometry": {"BoundingBox": {"Top": top, "Left": left, "Width": 0.4, "Height": 0.05}},
    }


def test_detect_text_reads_lines_in_order_with_confidence_filter(tmp_path: Path) -> None:
    client = _client("rekognition")
    reader = RekognitionTextReader(client, _settings(), Cassette(tmp_path, "live"))
    image = b"scan"
    detections = [
        _line("PRIYA SHAH", 0.4, 0.1),
        _line("LOW CONF", 0.2, 0.0, confidence=40.0),
        _line("FRAGILE", 0.1, 0.3),
        _line("EMPTY", 0.5, 0.5).copy() | {"DetectedText": ""},
        {"Type": "WORD", "DetectedText": "ignored", "Confidence": 99.0},
    ]
    with Stubber(client) as stubber:
        stubber.add_response(
            "detect_text",
            {"TextDetections": detections},
            {"Image": {"Bytes": image}},
        )
        assert asyncio.run(reader.read(image)) == ("FRAGILE", "PRIYA SHAH")


def test_detect_text_replay_matches_recording(tmp_path: Path) -> None:
    """DetectText answers replay byte-identical under the cassette key."""
    client = _client("rekognition")
    reader = RekognitionTextReader(client, _settings(), Cassette(tmp_path, "record"))
    image = b"scan"
    with Stubber(client) as stubber:
        stubber.add_response(
            "detect_text",
            {"TextDetections": [_line("FRAGILE", 0.1, 0.3)]},
            {"Image": {"Bytes": image}},
        )
        assert asyncio.run(reader.read(image)) == ("FRAGILE",)
        stubber.deactivate()
    replay = RekognitionTextReader(client, _settings(), Cassette(tmp_path, "replay"))
    assert asyncio.run(replay.read(image)) == ("FRAGILE",)


def test_detect_text_client_error_is_port_error(tmp_path: Path) -> None:
    client = _client("rekognition")
    reader = RekognitionTextReader(client, _settings(), Cassette(tmp_path, "live"))
    with Stubber(client) as stubber:
        stubber.add_client_error("detect_text", "InvalidImageFormatException")
        with pytest.raises(PortError, match=re.escape("rekognition.detect_text")):
            asyncio.run(reader.read(b"img"))


# --- PollySpeech ------------------------------------------------------------


def test_polly_synthesizes_once_and_memoises(tmp_path: Path) -> None:
    client = _client("polly")
    media = FileMediaStore(tmp_path / "media", "")
    speech = PollySpeech(client, _settings(), Cassette(tmp_path, "live"), media)
    audio = StreamingBody(io.BytesIO(b"mp3-bytes"), len("mp3-bytes"))

    with Stubber(client) as stubber:
        stubber.add_response(
            "synthesize_speech",
            {"AudioStream": audio},
            {
                "OutputFormat": "mp3",
                "Text": "one box for Priya",
                "VoiceId": "Danielle",
                "Engine": "neural",
            },
        )
        key = asyncio.run(speech.synthesize("one box for Priya"))
        # Second call returns the same key without hitting the client.
        again = asyncio.run(speech.synthesize("one box for Priya"))
        assert again == key
        stubber.assert_no_pending_responses()
    assert key.endswith(".mp3")
    assert (tmp_path / "media" / key).read_bytes() == b"mp3-bytes"


def test_polly_client_error_is_port_error(tmp_path: Path) -> None:
    client = _client("polly")
    media = FileMediaStore(tmp_path / "media", "")
    speech = PollySpeech(client, _settings(), Cassette(tmp_path, "live"), media)
    with Stubber(client) as stubber:
        stubber.add_client_error("synthesize_speech", "ServiceFailureException")
        with pytest.raises(PortError, match=re.escape("polly.synthesize_speech")):
            asyncio.run(speech.synthesize("hello"))
