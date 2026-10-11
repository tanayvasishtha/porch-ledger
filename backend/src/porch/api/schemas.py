"""Pydantic response and request models for the REST surface."""

from pydantic import BaseModel, Field

from porch.domain import RecipientState

PROBLEM_MEDIA_TYPE = "application/problem+json"


class VisitCard(BaseModel):
    id: str
    kind: str
    start_ms: int
    end_ms: int
    title: str
    span: str
    facts: tuple[str, ...]
    description: str
    hero_url: str | None
    clip_url: str | None
    recipient_id: str | None
    blocks_door: bool | None
    claimed_by: str | None
    provenance: str
    version: int


class SpeechRequest(BaseModel):
    text: str = Field(max_length=300)


class SpeechOut(BaseModel):
    url: str


class Folded(BaseModel):
    cars_passed: int
    activity: int


class VisitList(BaseModel):
    house_id: str
    day: str
    version: int
    cards: tuple[VisitCard, ...]
    folded: Folded


class BoxOut(BaseModel):
    x: float
    y: float
    w: float
    h: float
    recipient_id: str | None
    recipient_state: RecipientState
    blocks_door: bool | None


class ToolCallOut(BaseModel):
    tool: str
    ok: bool
    latency_ms: int
    note: str


class VisitDetail(VisitCard):
    box: BoxOut | None
    door_overlap: float | None
    trace: list[ToolCallOut]
    door_polygon: list[list[float]] | None


class ResidentOut(BaseModel):
    id: str
    display_name: str


class Inbox(BaseModel):
    spoken: str
    items: list[VisitCard]


class ClaimRequest(BaseModel):
    resident_id: str


class Problem(BaseModel):
    type: str
    title: str
    status: int
    detail: str
