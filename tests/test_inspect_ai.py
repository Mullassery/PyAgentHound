"""Inspect AI conversion tests (no inspect install required)."""

from __future__ import annotations

from pyagenthound.integrations.inspect_ai import trace_to_sample, traces_to_dataset
from pyagenthound.sdk.models import Span, SpanStatus, SpanType, Trace


def _trace():
    return Trace(
        trace_id="t1",
        name="agent",
        status=SpanStatus.OK,
        spans=[
            Span(
                trace_id="t1",
                name="tool",
                span_type=SpanType.TOOL,
                input={"q": "x"},
                output="ok",
                status=SpanStatus.OK,
            ),
            Span(
                trace_id="t1",
                name="llm",
                span_type=SpanType.LLM,
                output="final",
                status=SpanStatus.OK,
            ),
        ],
    )


def test_trace_to_sample_uses_inputs_and_last_output():
    sample = trace_to_sample(_trace())
    assert sample["id"] == "t1"
    assert "{'q': 'x'}" in sample["input"]
    assert sample["target"] == "final"
    assert sample["metadata"]["status"] == "OK"


def test_traces_to_dataset():
    assert len(traces_to_dataset([_trace(), _trace()])) == 2
