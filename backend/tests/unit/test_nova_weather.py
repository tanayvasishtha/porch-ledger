"""Nova describer and Open-Meteo weather tests: Stubber + MockTransport."""

import asyncio
import json
import re
from pathlib import Path
from typing import Any, Literal

import boto3
import httpx2
import pytest
from botocore.stub import Stubber

from porch.adapters.aws import (
    NovaDescriber,
    RekognitionLabeler,
    S3MediaStore,
    build_live_ports,
)
from porch.adapters.cassette import Cassette
from porch.adapters.openmeteo import OpenMeteoWeather
from porch.config import AwsSettings, Settings, WeatherSettings
from porch.domain import RainRisk
from porch.ports import PortError
from tests.helpers import FakeClock, demo_house


def _client(name: str) -> Any:
    return boto3.Session(
        region_name="us-east-1",
        aws_access_key_id="test",
        aws_secret_access_key="test",
    ).client(name)  # type: ignore[call-overload]


def _settings(**vision: Any) -> Settings:
    return Settings(
        aws=AwsSettings(media_bucket="porch-media"),
        vision=Settings().vision.model_copy(update=vision),
    )


def _describer(
    tmp_path: Path, mode: Literal["live", "record", "replay"] = "live"
) -> tuple[NovaDescriber, Any]:
    client = _client("bedrock-runtime")
    settings = _settings()
    media = S3MediaStore(_client("s3"), settings, Cassette(tmp_path / "s3", "live"))
    return NovaDescriber(client, media, settings, Cassette(tmp_path, mode)), client


def _converse_response(text: str) -> dict[str, Any]:
    return {
        "output": {"message": {"role": "assistant", "content": [{"text": text}]}},
        "stopReason": "end_turn",
        "usage": {"inputTokens": 1, "outputTokens": 1, "totalTokens": 2},
        "metrics": {"latencyMs": 1},
    }


def _describe(describer: NovaDescriber, client: Any, text: str) -> str | None:
    with Stubber(client) as stubber:
        stubber.add_response("converse", _converse_response(text))
        return asyncio.run(describer.describe("a1b2.mp4"))


def test_nova_valid_summary(tmp_path: Path) -> None:
    describer, client = _describer(tmp_path)
    body = '{"summary": "A van stops and a box is left.", "uncertain": false}'
    out = _describe(describer, client, body)
    assert out == "A van stops and a box is left."


def test_nova_fenced_json(tmp_path: Path) -> None:
    describer, client = _describer(tmp_path)
    fenced = '```json\n{"summary": "A person arrives.", "uncertain": false}\n```'
    assert _describe(describer, client, fenced) == "A person arrives."


def test_nova_uncertain_returns_none(tmp_path: Path) -> None:
    describer, client = _describer(tmp_path)
    body = '{"summary": "A person arrives.", "uncertain": true}'
    assert _describe(describer, client, body) is None


def test_nova_too_long_returns_none(tmp_path: Path) -> None:
    describer, client = _describer(tmp_path)
    long_summary = "x" * 200
    body = json.dumps({"summary": long_summary, "uncertain": False})
    assert _describe(describer, client, body) is None


def test_nova_accusation_returns_none(tmp_path: Path) -> None:
    describer, client = _describer(tmp_path)
    body = '{"summary": "Someone stolen the box.", "uncertain": false}'
    assert _describe(describer, client, body) is None


def test_nova_invalid_json_returns_none(tmp_path: Path) -> None:
    describer, client = _describer(tmp_path)
    assert _describe(describer, client, "not json") is None
    assert _describe(describer, client, '{"summary": "", "uncertain": false}') is None


def test_nova_client_error_is_port_error(tmp_path: Path) -> None:
    describer, client = _describer(tmp_path)
    with Stubber(client) as stubber:
        stubber.add_client_error("converse", "ThrottlingException")
        with pytest.raises(PortError, match=re.escape("bedrock.converse")):
            asyncio.run(describer.describe("a1b2.mp4"))


def test_nova_video_format_from_suffix(tmp_path: Path) -> None:
    describer, client = _describer(tmp_path, mode="record")
    with Stubber(client) as stubber:
        stubber.add_response(
            "converse", _converse_response('{"summary": "s.", "uncertain": false}')
        )
        asyncio.run(describer.describe("deadbeef.mov"))
    envelope = next(Cassette(tmp_path, "live").root.glob("nova_converse/v1/*.json"))
    request = json.loads(envelope.read_text())["request"]
    assert request["video_format"] == "mov"
    assert request["clip_uri"] == "s3://porch-media/deadbeef.mov"


def test_nova_unknown_suffix_is_port_error(tmp_path: Path) -> None:
    describer, _ = _describer(tmp_path)
    with pytest.raises(PortError, match=re.escape("unknown clip format")):
        asyncio.run(describer.describe("deadbeef.unknownext"))


# --- OpenMeteoWeather -------------------------------------------------------


def _weather_response(probs: list[int], first_hour: str = "2026-06-01T13:00") -> dict[str, Any]:
    hours = [f"2026-06-01T{h:02d}:00" for h in range(13, 13 + len(probs))]
    hours[0] = first_hour
    return {"hourly": {"time": hours, "precipitation_probability": probs}}


def _weather(
    tmp_path: Path, responses: list[httpx2.Response], clock: FakeClock | None = None
) -> tuple[OpenMeteoWeather, list[httpx2.Request]]:
    calls: list[httpx2.Request] = []

    def handler(request: httpx2.Request) -> httpx2.Response:
        calls.append(request)
        return responses[min(len(calls) - 1, len(responses) - 1)]

    settings = Settings(
        weather=WeatherSettings(base_url="https://test.local/v1/forecast"),
    )
    weather = OpenMeteoWeather(
        demo_house(),
        settings,
        clock or FakeClock(1_000_000),
        Cassette(tmp_path, "live"),
        client=httpx2.AsyncClient(transport=httpx2.MockTransport(handler)),
    )
    return weather, calls


def test_openmeteo_max_and_first_hour(tmp_path: Path) -> None:
    weather, calls = _weather(
        tmp_path, [httpx2.Response(200, json=_weather_response([10, 70, 70, 40]))]
    )
    risk = asyncio.run(weather.max_rain_probability_pct(4))
    assert risk == RainRisk(probability_pct=70, by_local_time="2:00 pm")
    assert "hourly=precipitation_probability" in str(calls[0].url)
    assert "latitude=47.6205" in str(calls[0].url)
    assert "forecast_hours=4" in str(calls[0].url)


def test_openmeteo_pm_formatting(tmp_path: Path) -> None:
    weather, _ = _weather(
        tmp_path,
        [httpx2.Response(200, json=_weather_response([55, 10], first_hour="2026-06-01T16:00"))],
    )
    risk = asyncio.run(weather.max_rain_probability_pct(2))
    assert risk == RainRisk(probability_pct=55, by_local_time="4:00 pm")


def test_openmeteo_cache_hit_and_ttl_miss(tmp_path: Path) -> None:
    clock = FakeClock(1_000_000)
    weather, calls = _weather(
        tmp_path, [httpx2.Response(200, json=_weather_response([30]))], clock=clock
    )
    assert asyncio.run(weather.max_rain_probability_pct(3)) is not None
    assert asyncio.run(weather.max_rain_probability_pct(3)) is not None
    assert len(calls) == 1  # cached within TTL
    clock.current += 901_000  # past the 900 s TTL
    assert asyncio.run(weather.max_rain_probability_pct(3)) is not None
    assert len(calls) == 2


def test_openmeteo_http_error_is_port_error(tmp_path: Path) -> None:
    weather, _ = _weather(tmp_path, [httpx2.Response(500, json={})])
    with pytest.raises(PortError, match=re.escape("openmeteo.forecast")):
        asyncio.run(weather.max_rain_probability_pct(3))


def test_openmeteo_no_data_returns_none(tmp_path: Path) -> None:
    weather, _ = _weather(tmp_path, [httpx2.Response(200, json={})])
    assert asyncio.run(weather.max_rain_probability_pct(3)) is None


def test_build_live_ports_wires_all(tmp_path: Path) -> None:
    enrich, labeler, media = build_live_ports(
        _settings(), demo_house(), FakeClock(0), Cassette(tmp_path, "live")
    )
    assert isinstance(enrich.describer, NovaDescriber)
    assert isinstance(enrich.weather, OpenMeteoWeather)
    assert enrich.media is media
    assert isinstance(labeler, RekognitionLabeler)
