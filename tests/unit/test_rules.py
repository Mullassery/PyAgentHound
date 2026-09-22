from pyagenthound.graph.builder import build_graph
from pyagenthound.rules.builtin import (
    DanglingParentSpanRule,
    DuplicateRetrievedDocumentsRule,
    EmptyRetrievalRule,
    StaleRetrievalDocumentsRule,
    ToolFailureRule,
)
from pyagenthound.rules.engine import run_rules
from pyagenthound.rules.models import FailureCategory, Severity
from pyagenthound.sdk.models import Span, SpanError, SpanStatus, SpanType, Trace


def _graph_for(trace: Trace):
    return build_graph(trace)


def test_empty_retrieval_rule_flags_zero_documents():
    trace = Trace(name="t")
    span = Span(
        trace_id=trace.trace_id,
        name="retrieval",
        span_type=SpanType.RETRIEVAL,
        attributes={"query": "q", "documents": []},
    )
    trace.spans = [span]

    findings = EmptyRetrievalRule().evaluate(trace, _graph_for(trace))

    assert len(findings) == 1
    assert findings[0].category == FailureCategory.RETRIEVAL_FAILURE
    assert findings[0].severity == Severity.HIGH
    assert findings[0].affected_nodes == [span.span_id]


def test_empty_retrieval_rule_ignores_nonempty_results():
    trace = Trace(name="t")
    span = Span(
        trace_id=trace.trace_id,
        name="retrieval",
        span_type=SpanType.RETRIEVAL,
        attributes={"documents": ["doc1"]},
    )
    trace.spans = [span]

    assert EmptyRetrievalRule().evaluate(trace, _graph_for(trace)) == []


def test_stale_retrieval_documents_rule_flags_older_documents():
    trace = Trace(name="t")
    span = Span(
        trace_id=trace.trace_id,
        name="retrieval",
        span_type=SpanType.RETRIEVAL,
        attributes={
            "documents": [
                {"id": "policy-2024", "date": "2024-01-01"},
                {"id": "policy-2026", "date": "2026-01-01"},
            ]
        },
    )
    trace.spans = [span]

    findings = StaleRetrievalDocumentsRule().evaluate(trace, _graph_for(trace))

    assert len(findings) == 1
    finding = findings[0]
    assert finding.category == FailureCategory.RETRIEVAL_FAILURE
    assert "doc:policy-2024" in finding.affected_nodes
    assert "doc:policy-2026" not in finding.affected_nodes
    assert 0.5 <= finding.confidence <= 0.95


def test_stale_retrieval_documents_rule_ignores_same_dated_documents():
    trace = Trace(name="t")
    span = Span(
        trace_id=trace.trace_id,
        name="retrieval",
        span_type=SpanType.RETRIEVAL,
        attributes={
            "documents": [
                {"id": "a", "date": "2026-01-01"},
                {"id": "b", "date": "2026-01-01"},
            ]
        },
    )
    trace.spans = [span]

    assert StaleRetrievalDocumentsRule().evaluate(trace, _graph_for(trace)) == []


def test_stale_retrieval_documents_rule_needs_at_least_two_dated_docs():
    trace = Trace(name="t")
    span = Span(
        trace_id=trace.trace_id,
        name="retrieval",
        span_type=SpanType.RETRIEVAL,
        attributes={"documents": [{"id": "a", "date": "2026-01-01"}, "undated-doc"]},
    )
    trace.spans = [span]

    assert StaleRetrievalDocumentsRule().evaluate(trace, _graph_for(trace)) == []


def test_duplicate_retrieved_documents_rule_flags_repeats():
    trace = Trace(name="t")
    span = Span(
        trace_id=trace.trace_id,
        name="retrieval",
        span_type=SpanType.RETRIEVAL,
        attributes={"documents": ["a", "a", "b"]},
    )
    trace.spans = [span]

    findings = DuplicateRetrievedDocumentsRule().evaluate(trace, _graph_for(trace))

    assert len(findings) == 1
    assert findings[0].severity == Severity.LOW
    assert findings[0].evidence[0].data["document_id"] == "a"
    assert findings[0].evidence[0].data["count"] == 2


def test_duplicate_retrieved_documents_rule_ignores_unique_documents():
    trace = Trace(name="t")
    span = Span(
        trace_id=trace.trace_id,
        name="retrieval",
        span_type=SpanType.RETRIEVAL,
        attributes={"documents": ["a", "b"]},
    )
    trace.spans = [span]

    assert DuplicateRetrievedDocumentsRule().evaluate(trace, _graph_for(trace)) == []


def test_tool_failure_rule_flags_error_status():
    trace = Trace(name="t")
    span = Span(
        trace_id=trace.trace_id,
        name="lookup_order",
        span_type=SpanType.TOOL,
        status=SpanStatus.ERROR,
        error=SpanError(type="ValueError", message="bad args"),
    )
    trace.spans = [span]

    findings = ToolFailureRule().evaluate(trace, _graph_for(trace))

    assert len(findings) == 1
    assert findings[0].category == FailureCategory.TOOL_FAILURE
    assert "bad args" in findings[0].description


def test_tool_failure_rule_ignores_successful_calls():
    trace = Trace(name="t")
    span = Span(
        trace_id=trace.trace_id, name="lookup_order", span_type=SpanType.TOOL, status=SpanStatus.OK
    )
    trace.spans = [span]

    assert ToolFailureRule().evaluate(trace, _graph_for(trace)) == []


def test_dangling_parent_span_rule_flags_missing_parent():
    trace = Trace(name="t")
    span = Span(
        trace_id=trace.trace_id,
        parent_span_id="does-not-exist",
        name="orphan",
        span_type=SpanType.TOOL,
    )
    trace.spans = [span]

    findings = DanglingParentSpanRule().evaluate(trace, _graph_for(trace))

    assert len(findings) == 1
    assert findings[0].category == FailureCategory.CONFIGURATION_FAILURE


def test_dangling_parent_span_rule_ignores_resolved_parent():
    trace = Trace(name="t")
    parent = Span(trace_id=trace.trace_id, name="parent", span_type=SpanType.AGENT)
    child = Span(
        trace_id=trace.trace_id,
        parent_span_id=parent.span_id,
        name="child",
        span_type=SpanType.TOOL,
    )
    trace.spans = [parent, child]

    assert DanglingParentSpanRule().evaluate(trace, _graph_for(trace)) == []


def test_run_rules_aggregates_across_builtin_rules():
    trace = Trace(name="t")
    retrieval = Span(
        trace_id=trace.trace_id,
        name="retrieval",
        span_type=SpanType.RETRIEVAL,
        attributes={"documents": []},
    )
    tool = Span(
        trace_id=trace.trace_id,
        name="tool",
        span_type=SpanType.TOOL,
        status=SpanStatus.ERROR,
        error=SpanError(type="TimeoutError", message="timed out"),
    )
    trace.spans = [retrieval, tool]

    findings = run_rules(trace, _graph_for(trace))

    rule_ids = {f.rule_id for f in findings}
    assert "empty_retrieval" in rule_ids
    assert "tool_failure" in rule_ids
