import pytest
from pydantic import ValidationError

from porch.config import EngineSettings, Settings


def test_defaults() -> None:
    s = Settings()
    assert s.mode == "replay"
    assert s.house_id == "demo"
    assert s.fixtures_dir.name == "fixtures"
    assert s.ring.base_url == "https://api.amazonvision.com"
    assert s.ring.poll_interval_s == 60
    assert s.ring.clip_max_duration_ms == 900_000
    assert s.engine.visit_merge_gap_s == 120
    assert s.engine.dwell_min_s == 45
    assert s.vision.recipient_min_score == 85
    assert s.vision.label_map["Van"] == "vehicle"
    assert s.vision.label_map["Package Delivery"] == "box"
    assert s.weather.rain_prob_threshold_pct == 50
    assert s.agent.model_id == "us.amazon.nova-lite-v1:0"
    assert s.aws.region == "us-east-1"
    assert s.api.media_url_ttl_s == 600


def test_env_override(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("PORCH_ENGINE__DWELL_MIN_S", "30")
    monkeypatch.setenv("PORCH_MODE", "record")
    s = Settings()
    assert s.engine.dwell_min_s == 30
    assert s.mode == "record"


def test_nested_env_override(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("PORCH_AWS__REGION", "eu-west-1")
    assert Settings().aws.region == "eu-west-1"


def test_constraint_rejection() -> None:
    with pytest.raises(ValidationError):
        EngineSettings(dwell_min_s=0)
    with pytest.raises(ValidationError):
        EngineSettings(box_match_iou=1.5)
    with pytest.raises(ValidationError):
        EngineSettings(box_min_frames=0)


def test_settings_frozen() -> None:
    s = Settings()
    with pytest.raises(ValidationError):
        s.mode = "live"  # type: ignore[misc]
