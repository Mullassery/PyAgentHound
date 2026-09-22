"""Root-cause hypothesis domain model. See docs/architecture.md section 6."""

from __future__ import annotations

import uuid

from pydantic import BaseModel, Field

from pyagenthound.rules.models import Evidence, FailureCategory


def _new_hypothesis_id() -> str:
    return f"hypothesis_{uuid.uuid4().hex[:12]}"


class ConfidenceComponents(BaseModel):
    """The decomposed confidence model (product spec section 6.7).

    Only the two components that are honestly computable without historical data are
    ever populated. `temporal_correlation` and `historical_frequency` require
    baseline storage (product spec section 6.8, not built) and stay `None` rather
    than being filled with a fabricated value.
    """

    evidence_strength: float
    causal_proximity: float
    temporal_correlation: float | None = None
    historical_frequency: float | None = None


class RootCauseHypothesis(BaseModel):
    hypothesis_id: str = Field(default_factory=_new_hypothesis_id)
    finding_id: str
    rule_id: str
    category: FailureCategory
    label: str
    """"likely_cause" for the top-ranked hypothesis, "contributing_factor" otherwise."""
    statement: str
    evidence: list[Evidence] = Field(default_factory=list)
    affected_nodes: list[str] = Field(default_factory=list)
    confidence: float = Field(ge=0.0, le=1.0)
    confidence_components: ConfidenceComponents
    recommendation: str | None = None
