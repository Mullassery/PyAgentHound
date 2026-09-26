import pytest

from pyagenthound.replay.engine import UnsafeReplayError, apply_overrides, build_plan, run_replay
from pyagenthound.replay.models import SafetyLevel
from pyagenthound.replay.safety import classify_span_safety
from pyagenthound.sdk.models import Span, SpanType, Trace
from pyagenthound.storage.sqlite_store import SQLiteTraceStore


def test_classify_span_safety_defaults():
    assert classify_span_safety(Span(trace_id="t", name="s", span_type=SpanType.RETRIEVAL)) == (
        SafetyLevel.READ_ONLY
    )
    assert classify_span_safety(Span(trace_id="t", name="s", span_type=SpanType.LLM)) == (
        SafetyLevel.READ_ONLY
    )
    assert classify_span_safety(Span(trace_id="t", name="s", span_type=SpanType.TOOL)) == (
        SafetyLevel.UNKNOWN
    )
    assert classify_span_safety(Span(trace_id="t", name="s", span_type=SpanType.MCP)) == (
        SafetyLevel.UNKNOWN
    )


def test_classify_span_safety_honors_explicit_attribute():
    span = Span(
        trace_id="t",
        name="s",
        span_type=SpanType.TOOL,
        attributes={"safety": "destructive"},
    )
    assert classify_span_safety(span) == SafetyLevel.DESTRUCTIVE


def test_classify_span_safety_ignores_invalid_declared_value():
    span = Span(trace_id="t", name="s", span_type=SpanType.TOOL, attributes={"safety": "nonsense"})
    assert classify_span_safety(span) == SafetyLevel.UNKNOWN


def test_build_plan_marks_unsafe_overridden_steps():
    trace = Trace(name="t")
    retrieval = Span(trace_id=trace.trace_id, name="retrieval", span_type=SpanType.RETRIEVAL)
    tool = Span(trace_id=trace.trace_id, name="tool", span_type=SpanType.TOOL)
    trace.spans = [retrieval, tool]

    plan = build_plan(trace, {tool.span_id: {"args": {}}})

    assert plan.requires_confirmation
    assert [s.span_id for s in plan.unsafe_steps] == [tool.span_id]


def test_build_plan_read_only_override_does_not_require_confirmation():
    trace = Trace(name="t")
    retrieval = Span(trace_id=trace.trace_id, name="retrieval", span_type=SpanType.RETRIEVAL)
    trace.spans = [retrieval]

    plan = build_plan(trace, {retrieval.span_id: {"documents": []}})

    assert not plan.requires_confirmation


def test_apply_overrides_clones_with_new_ids_and_applies_attributes():
    trace = Trace(name="t")
    retrieval = Span(
        trace_id=trace.trace_id,
        name="retrieval",
        span_type=SpanType.RETRIEVAL,
        attributes={"documents": ["a", "b"]},
    )
    llm = Span(
        trace_id=trace.trace_id,
        parent_span_id=retrieval.span_id,
        name="llm",
        span_type=SpanType.LLM,
    )
    trace.spans = [retrieval, llm]

    replayed = apply_overrides(trace, {retrieval.span_id: {"documents": ["a"]}})

    assert replayed.trace_id != trace.trace_id
    assert "replay" in replayed.tags
    assert replayed.metadata["replayed_from"] == trace.trace_id
    assert len(replayed.spans) == 2
    new_retrieval = next(s for s in replayed.spans if s.name == "retrieval")
    new_llm = next(s for s in replayed.spans if s.name == "llm")
    assert new_retrieval.span_id != retrieval.span_id
    assert new_retrieval.attributes["documents"] == ["a"]
    assert new_llm.parent_span_id == new_retrieval.span_id
    # original trace is untouched
    assert retrieval.attributes["documents"] == ["a", "b"]


def test_run_replay_resolves_finding(tmp_path):
    store = SQLiteTraceStore(tmp_path / "t.db")
    trace = Trace(name="t")
    retrieval = Span(
        trace_id=trace.trace_id,
        name="retrieval",
        span_type=SpanType.RETRIEVAL,
        attributes={
            "documents": [
                {"id": "a", "date": "2024-01-01"},
                {"id": "b", "date": "2026-01-01"},
            ]
        },
    )
    trace.spans = [retrieval]
    store.save_trace(trace)

    result = run_replay(
        store,
        trace,
        {retrieval.span_id: {"documents": [{"id": "b", "date": "2026-01-01"}]}},
    )

    assert "stale_retrieval_documents" in result.resolved_rule_ids
    assert result.new_rule_ids == []
    assert store.get_trace(result.replayed_trace_id) is not None


def test_run_replay_requires_confirmation_for_unsafe_override(tmp_path):
    store = SQLiteTraceStore(tmp_path / "t.db")
    trace = Trace(name="t")
    tool = Span(trace_id=trace.trace_id, name="tool", span_type=SpanType.TOOL)
    trace.spans = [tool]
    store.save_trace(trace)

    with pytest.raises(UnsafeReplayError):
        run_replay(store, trace, {tool.span_id: {"args": {}}})

    result = run_replay(store, trace, {tool.span_id: {"args": {}}}, allow_unsafe=True)
    assert result.replayed_trace_id != trace.trace_id
