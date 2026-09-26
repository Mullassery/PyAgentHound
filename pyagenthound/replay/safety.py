"""Span safety classification. See docs/architecture.md section 13.

Conservative by design: only span types that are near-universally side-effect-free
default to READ_ONLY. Everything else — including TOOL, MCP, API, DATABASE, and
MEMORY, all of which routinely mutate external state — defaults to UNKNOWN unless
the developer explicitly annotates `span.set_attribute("safety", "READ_ONLY")` (or
WRITE/DESTRUCTIVE) at capture time. UNKNOWN is treated the same as WRITE/DESTRUCTIVE
for confirmation purposes (see `ReplayPlan.requires_confirmation`) — an unannotated
span is never assumed safe.
"""

from __future__ import annotations

from pyagenthound.replay.models import SafetyLevel
from pyagenthound.sdk.models import Span, SpanType

_READ_ONLY_DEFAULTS = frozenset(
    {SpanType.RETRIEVAL, SpanType.EMBEDDING, SpanType.RERANKING, SpanType.LLM, SpanType.PROMPT}
)


def classify_span_safety(span: Span) -> SafetyLevel:
    declared = span.attributes.get("safety")
    if isinstance(declared, str):
        try:
            return SafetyLevel(declared.upper())
        except ValueError:
            pass
    if span.span_type in _READ_ONLY_DEFAULTS:
        return SafetyLevel.READ_ONLY
    return SafetyLevel.UNKNOWN
