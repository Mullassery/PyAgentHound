"""Finding domain model + rule engine interface. See docs/architecture.md section 5.

Findings are detected anomalies, not root causes — they never claim to explain
*why* something went wrong, only *what* deterministically looks wrong and what
evidence supports that. The root-cause engine (Phase 4, not built) is what turns a
set of findings into ranked, evidence-referenced hypotheses.
"""

from __future__ import annotations

import uuid
from enum import Enum
from typing import Any, Protocol

from pydantic import BaseModel, Field

from pyagenthound.graph.models import ExecutionGraph
from pyagenthound.sdk.models import Trace


def _new_finding_id() -> str:
    return f"finding_{uuid.uuid4().hex[:12]}"


class FailureCategory(str, Enum):
    RETRIEVAL_FAILURE = "RETRIEVAL_FAILURE"
    TOOL_FAILURE = "TOOL_FAILURE"
    MODEL_FAILURE = "MODEL_FAILURE"
    PROMPT_FAILURE = "PROMPT_FAILURE"
    CONTEXT_FAILURE = "CONTEXT_FAILURE"
    DATA_FAILURE = "DATA_FAILURE"
    API_FAILURE = "API_FAILURE"
    AGENT_LOOP = "AGENT_LOOP"
    MEMORY_FAILURE = "MEMORY_FAILURE"
    GUARDRAIL_FAILURE = "GUARDRAIL_FAILURE"
    PERFORMANCE_FAILURE = "PERFORMANCE_FAILURE"
    DEPENDENCY_FAILURE = "DEPENDENCY_FAILURE"
    CONFIGURATION_FAILURE = "CONFIGURATION_FAILURE"
    UNKNOWN = "UNKNOWN"


class Severity(str, Enum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


class Evidence(BaseModel):
    """A single observed fact backing a finding. Never an inference."""

    description: str
    data: dict[str, Any] = Field(default_factory=dict)


class Finding(BaseModel):
    finding_id: str = Field(default_factory=_new_finding_id)
    rule_id: str
    category: FailureCategory
    severity: Severity
    title: str
    description: str
    evidence: list[Evidence] = Field(default_factory=list)
    affected_nodes: list[str] = Field(default_factory=list)
    confidence: float = Field(ge=0.0, le=1.0)
    recommendation: str | None = None


class Rule(Protocol):
    """A pure, deterministic function over a trace + its execution graph.

    `id` and `category` are read as instance attributes (not called), so a rule can
    be a plain class with class-level `id`/`category` and an `evaluate` method — see
    `pyagenthound/rules/builtin.py`.
    """

    id: str
    category: FailureCategory

    def evaluate(self, trace: Trace, graph: ExecutionGraph) -> list[Finding]: ...
