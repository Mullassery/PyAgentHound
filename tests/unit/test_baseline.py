from datetime import datetime, timedelta, timezone

from pyagenthound.baseline.engine import (
    compare_to_baseline,
    find_baseline,
    historical_rule_frequencies,
)
from pyagenthound.baseline.signature import extract_signature
from pyagenthound.sdk.models import Span, SpanStatus, SpanType, Trace
from pyagenthound.storage.sqlite_store import SQLiteTraceStore

_T0 = datetime(2026, 1, 1, tzinfo=timezone.utc)


def _at(seconds: float) -> datetime:
    return _T0 + timedelta(seconds=seconds)


def test_extract_signature_aggregates_llm_retrieval_and_tools():
    trace = Trace(name="t", start_time=_at(0), end_time=_at(3))
    retrieval = Span(
        trace_id=trace.trace_id,
        name="retrieval",
        span_type=SpanType.RETRIEVAL,
        start_time=_at(0),
        attributes={"retriever": "hybrid-v3"},
    )
    llm = Span(
        trace_id=trace.trace_id,
        name="llm",
        span_type=SpanType.LLM,
        start_time=_at(1),
        attributes={
            "model": "gpt-4o",
            "prompt_version": "v1",
            "input_tokens": 100,
            "output_tokens": 20,
        },
    )
    tool = Span(
        trace_id=trace.trace_id, name="lookup_order", span_type=SpanType.TOOL, start_time=_at(2)
    )
    trace.spans = [retrieval, llm, tool]

    sig = extract_signature(trace)

    assert sig.model == "gpt-4o"
    assert sig.prompt_version == "v1"
    assert sig.retriever == "hybrid-v3"
    assert sig.tools == ["lookup_order"]
    assert sig.input_tokens == 100
    assert sig.output_tokens == 20
    assert sig.total_tokens == 120
    assert sig.execution_path == ["RETRIEVAL", "LLM", "TOOL"]


def test_extract_signature_total_tokens_none_when_no_llm_spans():
    trace = Trace(name="t")
    assert extract_signature(trace).total_tokens is None


def test_find_baseline_returns_most_recent_successful_same_name(tmp_path):
    store = SQLiteTraceStore(tmp_path / "t.db")
    old = Trace(name="checkout", status=SpanStatus.OK, start_time=_at(0))
    newer = Trace(name="checkout", status=SpanStatus.OK, start_time=_at(10))
    other_name = Trace(name="support", status=SpanStatus.OK, start_time=_at(20))
    for t in (old, newer, other_name):
        store.save_trace(t)
    current = Trace(name="checkout", status=SpanStatus.ERROR, start_time=_at(30))
    store.save_trace(current)

    baseline = find_baseline(store, current)

    assert baseline is not None
    assert baseline.trace_id == newer.trace_id


def test_find_baseline_returns_none_when_no_prior_success(tmp_path):
    store = SQLiteTraceStore(tmp_path / "t.db")
    current = Trace(name="checkout", status=SpanStatus.ERROR)
    store.save_trace(current)

    assert find_baseline(store, current) is None


def test_compare_to_baseline_detects_model_change():
    baseline = Trace(name="t")
    baseline.spans = [
        Span(
            trace_id=baseline.trace_id,
            name="llm",
            span_type=SpanType.LLM,
            attributes={"model": "gpt-4o"},
        )
    ]
    current = Trace(name="t")
    current.spans = [
        Span(
            trace_id=current.trace_id,
            name="llm",
            span_type=SpanType.LLM,
            attributes={"model": "gpt-4-turbo"},
        )
    ]

    findings = compare_to_baseline(current, baseline)

    assert any(f.rule_id == "baseline_model_changed" for f in findings)
    assert all(f.confidence == 1.0 for f in findings)


def test_compare_to_baseline_detects_execution_path_change():
    baseline = Trace(name="t")
    baseline.spans = [Span(trace_id=baseline.trace_id, name="llm", span_type=SpanType.LLM)]
    current = Trace(name="t")
    current.spans = [
        Span(trace_id=current.trace_id, name="retrieval", span_type=SpanType.RETRIEVAL),
        Span(trace_id=current.trace_id, name="llm", span_type=SpanType.LLM),
    ]

    findings = compare_to_baseline(current, baseline)

    assert any(f.rule_id == "baseline_execution_path_changed" for f in findings)


def test_compare_to_baseline_detects_latency_regression():
    baseline = Trace(name="t", start_time=_at(0), end_time=_at(1))
    current = Trace(name="t", start_time=_at(0), end_time=_at(2))

    findings = compare_to_baseline(current, baseline)

    assert any(f.rule_id == "baseline_latency_regression" for f in findings)


def test_compare_to_baseline_detects_token_growth():
    baseline = Trace(name="t")
    baseline.spans = [
        Span(
            trace_id=baseline.trace_id,
            name="llm",
            span_type=SpanType.LLM,
            attributes={"input_tokens": 100, "output_tokens": 50},
        )
    ]
    current = Trace(name="t")
    current.spans = [
        Span(
            trace_id=current.trace_id,
            name="llm",
            span_type=SpanType.LLM,
            attributes={"input_tokens": 500, "output_tokens": 50},
        )
    ]

    findings = compare_to_baseline(current, baseline)

    assert any(f.rule_id == "baseline_token_growth" for f in findings)


def test_compare_to_baseline_no_findings_when_nothing_changed():
    baseline = Trace(name="t", start_time=_at(0), end_time=_at(1))
    current = Trace(name="t", start_time=_at(0), end_time=_at(1))

    assert compare_to_baseline(current, baseline) == []


def test_historical_rule_frequencies_computes_fraction(tmp_path):
    store = SQLiteTraceStore(tmp_path / "t.db")
    for i in range(3):
        t = Trace(name="checkout", start_time=_at(i))
        if i < 2:
            t.spans = [
                Span(
                    trace_id=t.trace_id,
                    name="retrieval",
                    span_type=SpanType.RETRIEVAL,
                    attributes={"documents": []},
                )
            ]
        store.save_trace(t)
    current = Trace(name="checkout", start_time=_at(10))
    store.save_trace(current)

    freqs = historical_rule_frequencies(store, current)

    assert freqs["empty_retrieval"] == 2 / 3


def test_historical_rule_frequencies_empty_when_no_history(tmp_path):
    store = SQLiteTraceStore(tmp_path / "t.db")
    current = Trace(name="checkout")
    store.save_trace(current)

    assert historical_rule_frequencies(store, current) == {}
