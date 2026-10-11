"""Single Settings object for the whole backend.

Every threshold, window, model id and limit lives here. Values are
overridable through PORCH_ environment variables, with nested groups
joined by a double underscore (PORCH_ENGINE__DWELL_MIN_S=30).
"""

from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field
from pydantic_settings import BaseSettings, SettingsConfigDict

from porch.domain.porch_state import EngineParams


class RingSettings(BaseModel):
    model_config = ConfigDict(frozen=True)

    base_url: str = "https://api.amazonvision.com"
    poll_interval_s: int = Field(default=60, gt=0)
    request_timeout_s: int = Field(default=30, gt=0)
    max_retries: int = Field(default=1, ge=0)
    snapshots_per_event: int = Field(default=3, gt=0)
    clip_max_duration_ms: int = Field(default=900_000, gt=0)
    # Env var names; the secrets themselves never live in settings.
    access_token_env: str = "RING_ACCESS_TOKEN"
    webhook_secret_env: str = "RING_WEBHOOK_SECRET"
    history_page_limit: int = Field(default=5, gt=0)
    # Media Clips docs: on 416/425 retry the unchanged request with the
    # capped sequence 5, 10, 20, 30 then 30 s, up to about two minutes.
    media_retry_schedule_s: tuple[int, ...] = (5, 10, 20, 30, 30, 30)
    # Fractions of the event duration at which snapshots are requested.
    snapshot_offsets: tuple[float, ...] = (0.0, 0.5, 1.0)


class EngineSettings(BaseModel):
    model_config = ConfigDict(frozen=True)

    visit_merge_gap_s: int = Field(default=120, gt=0)
    box_match_iou: float = Field(default=0.3, ge=0.0, le=1.0)
    box_min_frames: int = Field(default=2, ge=1)
    dwell_min_s: int = Field(default=45, gt=0)
    min_detection_confidence: float = Field(default=0.6, ge=0.0, le=1.0)


class VisionSettings(BaseModel):
    model_config = ConfigDict(frozen=True)

    label_map: dict[str, Literal["vehicle", "person", "box"]] = {
        "Car": "vehicle",
        "Truck": "vehicle",
        "Van": "vehicle",
        "Person": "person",
        "Box": "box",
        "Package": "box",
        "Cardboard": "box",
        "Carton": "box",
        "Package Delivery": "box",
    }
    label_crop_margin: float = Field(default=0.15, ge=0.0, le=1.0)
    recipient_min_score: int = Field(default=85, ge=0, le=100)
    recipient_margin: int = Field(default=10, ge=0, le=100)
    door_block_overlap: float = Field(default=0.25, ge=0.0, le=1.0)
    # Confidence values below are Rekognition/Textract percentages, 0-100.
    ocr_min_confidence: float = Field(default=60.0, ge=0.0, le=100.0)
    rekognition_min_confidence: float = Field(default=60.0, ge=0.0, le=100.0)
    rekognition_max_labels: int = Field(default=25, gt=0)
    describe_model_id: str = "us.amazon.nova-lite-v1:0"
    describe_max_tokens: int = Field(default=200, gt=0)
    describe_max_chars: int = Field(default=140, gt=0)


class WeatherSettings(BaseModel):
    model_config = ConfigDict(frozen=True)

    base_url: str = "https://api.open-meteo.com/v1/forecast"
    timeout_s: int = Field(default=10, gt=0)
    rain_horizon_h: int = Field(default=3, gt=0)
    rain_prob_threshold_pct: int = Field(default=50, ge=0, le=100)
    cache_ttl_s: int = Field(default=900, gt=0)


class AgentSettings(BaseModel):
    model_config = ConfigDict(frozen=True)

    model_id: str = "us.amazon.nova-lite-v1:0"
    max_tool_calls: int = Field(default=6, gt=0)
    timeout_s: int = Field(default=45, gt=0)


class AwsSettings(BaseModel):
    model_config = ConfigDict(frozen=True)

    region: str = "us-east-1"
    media_bucket: str = ""
    polly_voice: str = "Danielle"
    polly_engine: Literal["neural", "generative", "standard"] = "neural"
    s3_concurrency: int = Field(default=4, gt=0)
    rekognition_concurrency: int = Field(default=4, gt=0)
    textract_concurrency: int = Field(default=2, gt=0)
    bedrock_concurrency: int = Field(default=2, gt=0)
    polly_concurrency: int = Field(default=2, gt=0)


class ApiSettings(BaseModel):
    model_config = ConfigDict(frozen=True)

    media_url_ttl_s: int = Field(default=600, gt=0)
    poll_hint_ms: int = Field(default=5000, gt=0)
    # None means open access; only acceptable for local replay development.
    house_key_sha256: str | None = None
    cors_origins: tuple[str, ...] = ()
    house_file: Path = Path("fixtures/house.demo.json")
    sqlite_path: Path = Path(".local/porch.db")
    local_media_dir: Path = Path(".local/media")
    # Empty means media URLs go out relative; clients resolve their own base.
    public_base_url: str = ""


class Settings(BaseSettings):
    """Root settings. fixtures_dir resolves relative to the working directory."""

    model_config = SettingsConfigDict(
        env_prefix="PORCH_",
        env_nested_delimiter="__",
        extra="forbid",
        frozen=True,
    )

    mode: Literal["live", "record", "replay"] = "replay"
    house_id: str = "demo"
    fixtures_dir: Path = Path("fixtures")
    ring: RingSettings = Field(default_factory=RingSettings)
    engine: EngineSettings = Field(default_factory=EngineSettings)
    vision: VisionSettings = Field(default_factory=VisionSettings)
    weather: WeatherSettings = Field(default_factory=WeatherSettings)
    agent: AgentSettings = Field(default_factory=AgentSettings)
    aws: AwsSettings = Field(default_factory=AwsSettings)
    api: ApiSettings = Field(default_factory=ApiSettings)


def from_settings(settings: EngineSettings) -> EngineParams:
    """Build the pydantic-free EngineParams the domain engine consumes."""
    return EngineParams(
        visit_merge_gap_s=settings.visit_merge_gap_s,
        box_match_iou=settings.box_match_iou,
        box_min_frames=settings.box_min_frames,
        dwell_min_s=settings.dwell_min_s,
        min_detection_confidence=settings.min_detection_confidence,
    )
