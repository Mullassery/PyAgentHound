"""Root-cause ranking. See docs/architecture.md section 6.

Turns each `Finding` into a `RootCauseHypothesis`, ranked by a confidence built from
two graph/evidence-derived components (no historical baseline exists yet — see
`ConfidenceComponents`), and labels the top-ranked hypothesis `likely_cause`.
"""

from __future__ import annotations

from pyagenthound.graph.models import ExecutionGraph, Relationship
from pyagenthound.rootcause.models import ConfidenceComponents, RootCauseHypothesis
from pyagenthound.rules.engine import run_rules
from pyagenthound.rules.models import Finding
from pyagenthound.sdk.models import Span, Trace

_EVIDENCE_STRENGTH_WEIGHT = 0.7
_CAUSAL_PROXIMITY_WEIGHT = 0.3
_OFF_PATH_PROXIMITY = 0.3


def rank_root_causes(
    trace: Trace, graph: ExecutionGraph, findings: list[Finding] | None = None
) -> list[RootCauseHypothesis]:
    if findings is None:
        findings = run_rules(trace, graph)
    if not findings:
        return []

    final_node_id = _final_node_id(trace)

    hypotheses = []
    for finding in findings:
        span_node_id = finding.affected_nodes[0] if finding.affected_nodes else final_node_id
        proximity = _causal_proximity(graph, span_node_id, final_node_id)
        components = ConfidenceComponents(
            evidence_strength=finding.confidence, causal_proximity=proximity
        )
        confidence = round(
            _EVIDENCE_STRENGTH_WEIGHT * components.evidence_strength
            + _CAUSAL_PROXIMITY_WEIGHT * components.causal_proximity,
            2,
        )
        hypotheses.append(
            RootCauseHypothesis(
                finding_id=finding.finding_id,
                rule_id=finding.rule_id,
                category=finding.category,
                label="contributing_factor",
                statement=finding.title,
                evidence=finding.evidence,
                affected_nodes=finding.affected_nodes,
                confidence=confidence,
                confidence_components=components,
                recommendation=finding.recommendation,
            )
        )

    hypotheses.sort(key=lambda h: h.confidence, reverse=True)
    hypotheses[0].label = "likely_cause"
    return hypotheses


def _final_node_id(trace: Trace) -> str:
    """The span with the latest `end_time` — a proxy for "produced the final output"."""
    completed: list[Span] = [s for s in trace.spans if s.end_time is not None]
    if not completed:
        return trace.trace_id
    latest = completed[0]
    for span in completed[1:]:
        if span.end_time is None or latest.end_time is None:
            continue
        if span.end_time > latest.end_time:
            latest = span
    return latest.span_id


def _causal_proximity(graph: ExecutionGraph, node_id: str, final_node_id: str) -> float:
    hops = _hops_to_ancestor(graph, final_node_id, node_id)
    if hops is not None:
        return round(1.0 / (1.0 + hops), 2)
    return _OFF_PATH_PROXIMITY


def _hops_to_ancestor(graph: ExecutionGraph, from_id: str, ancestor_id: str) -> int | None:
    """Walk `PARENT` edges upward from `from_id`; hop count to reach `ancestor_id`, or
    `None` if `ancestor_id` isn't on that path (a sibling branch, not an ancestor)."""
    if from_id == ancestor_id:
        return 0
    current = from_id
    hops = 0
    visited: set[str] = set()
    while True:
        parents = graph.incoming(current, relationship=Relationship.PARENT)
        if not parents:
            return None
        current = parents[0].source
        hops += 1
        if current == ancestor_id:
            return hops
        if current in visited:
            return None
        visited.add(current)
