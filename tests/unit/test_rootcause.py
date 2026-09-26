from datetime import datetime, timedelta, timezone

from pyagenthound.graph.builder import build_graph
from pyagenthound.rootcause.engine import (
    _causal_proximity,
    _combine_confidence,
    _hops_to_ancestor,
    rank_root_causes,
)
from pyagenthound.rootcause.models import ConfidenceComponents
from pyagenthound.sdk.models import Span, SpanError, SpanStatus, SpanType, Trace
from pyagenthound.storage.sqlite_store import SQLiteTraceStore

_T0 = datetime(2026, 1, 1, tzinfo=timezone.utc)


def _at(seconds: float) -> datetime:
    return _T0 + timedelta(seconds=seconds)


def test_rank_root_causes_empty_when_no_findings():
    trace = Trace(name="t")
    graph = build_graph(trace)

    assert rank_root_causes(trace, graph) == []


def test_rank_root_causes_single_finding_is_likely_cause():
    trace = Trace(name="t")
    span = Span(
        trace_id=trace.trace_id,
        name="retrieval",
        span_type=SpanType.RETRIEVAL,
        attributes={"documents": []},
    )
    trace.spans = [span]
    graph = build_graph(trace)

    hypotheses = rank_root_causes(trace, graph)

    assert len(hypotheses) == 1
    assert hypotheses[0].label == "likely_cause"
    assert hypotheses[0].confidence_components.temporal_correlation is None
    assert hypotheses[0].confidence_components.historical_frequency is None


def test_hops_to_ancestor_direct_parent():
    trace = Trace(name="t")
    parent = Span(trace_id=trace.trace_id, name="parent", span_type=SpanType.AGENT)
    child = Span(
        trace_id=trace.trace_id,
        parent_span_id=parent.span_id,
        name="child",
        span_type=SpanType.LLM,
    )
    trace.spans = [parent, child]
    graph = build_graph(trace)

    assert _hops_to_ancestor(graph, child.span_id, parent.span_id) == 1
    assert _hops_to_ancestor(graph, child.span_id, child.span_id) == 0


def test_hops_to_ancestor_returns_none_for_sibling():
    trace = Trace(name="t")
    parent = Span(trace_id=trace.trace_id, name="parent", span_type=SpanType.AGENT)
    a = Span(
        trace_id=trace.trace_id, parent_span_id=parent.span_id, name="a", span_type=SpanType.TOOL
    )
    b = Span(
        trace_id=trace.trace_id, parent_span_id=parent.span_id, name="b", span_type=SpanType.TOOL
    )
    trace.spans = [parent, a, b]
    graph = build_graph(trace)

    assert _hops_to_ancestor(graph, a.span_id, b.span_id) is None


def test_causal_proximity_decreases_with_distance():
    trace = Trace(name="t")
    root_span = Span(trace_id=trace.trace_id, name="agent", span_type=SpanType.AGENT)
    mid = Span(
        trace_id=trace.trace_id,
        parent_span_id=root_span.span_id,
        name="mid",
        span_type=SpanType.RETRIEVAL,
    )
    final = Span(
        trace_id=trace.trace_id, parent_span_id=mid.span_id, name="final", span_type=SpanType.LLM
    )
    trace.spans = [root_span, mid, final]
    graph = build_graph(trace)

    close = _causal_proximity(graph, mid.span_id, final.span_id)
    far = _causal_proximity(graph, root_span.span_id, final.span_id)

    assert close > far
    assert _causal_proximity(graph, final.span_id, final.span_id) == 1.0


def test_causal_proximity_off_path_uses_fixed_fallback():
    trace = Trace(name="t")
    agent = Span(trace_id=trace.trace_id, name="agent", span_type=SpanType.AGENT)
    tool = Span(trace_id=trace.trace_id, name="tool", span_type=SpanType.TOOL)
    trace.spans = [agent, tool]
    graph = build_graph(trace)

    assert _causal_proximity(graph, tool.span_id, agent.span_id) == 0.3


def test_rank_root_causes_orders_by_confidence_descending():
    trace = Trace(name="t")
    retrieval = Span(
        trace_id=trace.trace_id,
        name="retrieval",
        span_type=SpanType.RETRIEVAL,
        start_time=_at(0),
        end_time=_at(1),
        attributes={
            "documents": [
                {"id": "a", "date": "2024-01-01"},
                {"id": "b", "date": "2025-01-01"},
                {"id": "c", "date": "2026-01-01"},
            ]
        },
    )
    tool = Span(
        trace_id=trace.trace_id,
        name="tool",
        span_type=SpanType.TOOL,
        status=SpanStatus.ERROR,
        error=SpanError(type="TimeoutError", message="timed out"),
        start_time=_at(0),
        end_time=_at(2),
    )
    trace.spans = [retrieval, tool]
    graph = build_graph(trace)

    hypotheses = rank_root_causes(trace, graph)

    confidences = [h.confidence for h in hypotheses]
    assert confidences == sorted(confidences, reverse=True)
    assert hypotheses[0].label == "likely_cause"
    assert all(h.label == "contributing_factor" for h in hypotheses[1:])


def test_combine_confidence_two_components_renormalizes():
    components = ConfidenceComponents(evidence_strength=1.0, causal_proximity=0.5)

    expected = round((0.4 * 1.0 + 0.2 * 0.5) / (0.4 + 0.2), 2)
    assert _combine_confidence(components) == expected


def test_combine_confidence_all_four_components():
    components = ConfidenceComponents(
        evidence_strength=1.0,
        causal_proximity=0.5,
        temporal_correlation=1.0,
        historical_frequency=0.5,
    )

    expected = round(0.4 * 1.0 + 0.2 * 0.5 + 0.2 * 1.0 + 0.2 * 0.5, 2)
    assert _combine_confidence(components) == expected


def test_rank_root_causes_with_store_merges_baseline_and_sets_temporal_correlation(tmp_path):
    store = SQLiteTraceStore(tmp_path / "t.db")
    baseline = Trace(name="checkout", status=SpanStatus.OK, start_time=_at(0))
    baseline.spans = [
        Span(
            trace_id=baseline.trace_id,
            name="llm",
            span_type=SpanType.LLM,
            attributes={"model": "gpt-4o"},
        )
    ]
    store.save_trace(baseline)

    current = Trace(name="checkout", status=SpanStatus.ERROR, start_time=_at(10))
    current.spans = [
        Span(
            trace_id=current.trace_id,
            name="llm",
            span_type=SpanType.LLM,
            attributes={"model": "gpt-4-turbo"},
        )
    ]
    store.save_trace(current)

    graph = build_graph(current)
    hypotheses = rank_root_causes(current, graph, store=store)

    model_change = next(h for h in hypotheses if h.rule_id == "baseline_model_changed")
    assert model_change.confidence_components.temporal_correlation == 1.0


def test_rank_root_causes_without_store_leaves_temporal_and_historical_none():
    trace = Trace(name="t")
    trace.spans = [
        Span(
            trace_id=trace.trace_id,
            name="retrieval",
            span_type=SpanType.RETRIEVAL,
            attributes={"documents": []},
        )
    ]
    graph = build_graph(trace)

    hypotheses = rank_root_causes(trace, graph)

    assert hypotheses[0].confidence_components.temporal_correlation is None
    assert hypotheses[0].confidence_components.historical_frequency is None
