"""OpenTelemetry-compatible tracing domain model. See docs/architecture.md section 3.

Attributes/input/output are intentionally untyped (``Any``/``dict[str, Any]``)
rather than per-span-type subclasses — later rules/analyzers pattern-match on
whatever fields they care about and ignore the rest, so adding a new AI-specific
field never requires a model migration (product spec section 6.3).
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


def _new_trace_id() -> str:
    return uuid.uuid4().hex


def _new_span_id() -> str:
    return uuid.uuid4().hex[:16]


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class SpanType(str, Enum):
    AGENT = "AGENT"
    LLM = "LLM"
    RETRIEVAL = "RETRIEVAL"
    EMBEDDING = "EMBEDDING"
    RERANKING = "RERANKING"
    TOOL = "TOOL"
    MCP = "MCP"
    API = "API"
    DATABASE = "DATABASE"
    VECTOR_DB = "VECTOR_DB"
    PROMPT = "PROMPT"
    MEMORY = "MEMORY"
    GUARDRAIL = "GUARDRAIL"
    EVALUATION = "EVALUATION"
    CUSTOM = "CUSTOM"


class SpanStatus(str, Enum):
    UNSET = "UNSET"
    OK = "OK"
    ERROR = "ERROR"


class Event(BaseModel):
    name: str
    timestamp: datetime = Field(default_factory=_utcnow)
    attributes: dict[str, Any] = Field(default_factory=dict)


class SpanError(BaseModel):
    type: str
    message: str
    stacktrace: str | None = None


class Span(BaseModel):
    span_id: str = Field(default_factory=_new_span_id)
    trace_id: str
    parent_span_id: str | None = None
    name: str
    span_type: SpanType = SpanType.CUSTOM
    start_time: datetime = Field(default_factory=_utcnow)
    end_time: datetime | None = None
    status: SpanStatus = SpanStatus.UNSET
    status_message: str | None = None
    attributes: dict[str, Any] = Field(default_factory=dict)
    events: list[Event] = Field(default_factory=list)
    input: Any | None = None
    output: Any | None = None
    error: SpanError | None = None

    @property
    def duration_ms(self) -> float | None:
        if self.end_time is None:
            return None
        return (self.end_time - self.start_time).total_seconds() * 1000


class Trace(BaseModel):
    trace_id: str = Field(default_factory=_new_trace_id)
    name: str
    start_time: datetime = Field(default_factory=_utcnow)
    end_time: datetime | None = None
    status: SpanStatus = SpanStatus.UNSET
    tags: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)
    spans: list[Span] = Field(default_factory=list)

    @property
    def duration_ms(self) -> float | None:
        if self.end_time is None:
            return None
        return (self.end_time - self.start_time).total_seconds() * 1000


class TraceSummary(BaseModel):
    """Lightweight trace listing row — no spans. Used by `list_traces`/`GET /api/traces`."""

    trace_id: str
    name: str
    start_time: datetime
    end_time: datetime | None = None
    status: SpanStatus
    tags: list[str] = Field(default_factory=list)
    span_count: int = 0
