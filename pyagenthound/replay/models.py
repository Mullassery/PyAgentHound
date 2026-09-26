"""Replay domain model. See docs/architecture.md section 13.

Replay here means counterfactual attribute-override replay on a *cloned* trace, not
re-invoking the original agent code — PyAgentHound observes traces, it doesn't own
the agent's runtime, so it cannot honestly "call the LLM again" or "re-run the tool."
What it can do, and does: clone a trace, apply attribute overrides to specific spans
(e.g. "what if retrieval had returned only fresh documents?"), and re-run the finding
engine to see whether the anomaly clears. This is exactly the demo workflow in
product spec section 27 ("fix retrieval, replay, see it resolved").
"""

from __future__ import annotations

from enum import Enum
from typing import Any

from pydantic import BaseModel, Field

from pyagenthound.rules.models import Finding
from pyagenthound.sdk.models import SpanType


class SafetyLevel(str, Enum):
    READ_ONLY = "READ_ONLY"
    WRITE = "WRITE"
    DESTRUCTIVE = "DESTRUCTIVE"
    UNKNOWN = "UNKNOWN"


class ReplayStep(BaseModel):
    span_id: str
    name: str
    span_type: SpanType
    safety: SafetyLevel
    overrides: dict[str, Any] = Field(default_factory=dict)


class ReplayPlan(BaseModel):
    trace_id: str
    steps: list[ReplayStep] = Field(default_factory=list)

    @property
    def unsafe_steps(self) -> list[ReplayStep]:
        """Overridden steps whose safety isn't READ_ONLY — these need confirmation."""
        return [s for s in self.steps if s.overrides and s.safety != SafetyLevel.READ_ONLY]

    @property
    def requires_confirmation(self) -> bool:
        return len(self.unsafe_steps) > 0


class ReplayRequest(BaseModel):
    """Request body for `POST /api/traces/{id}/replay`. Keys of `overrides` are the
    *original* trace's span ids."""

    overrides: dict[str, dict[str, Any]] = Field(default_factory=dict)
    allow_unsafe: bool = False


class ReplayResult(BaseModel):
    original_trace_id: str
    replayed_trace_id: str
    plan: ReplayPlan
    original_findings: list[Finding] = Field(default_factory=list)
    replayed_findings: list[Finding] = Field(default_factory=list)
    resolved_rule_ids: list[str] = Field(default_factory=list)
    """rule_ids present in the original trace's findings but absent from the replay's."""
    new_rule_ids: list[str] = Field(default_factory=list)
    """rule_ids present in the replay's findings but absent from the original's."""
