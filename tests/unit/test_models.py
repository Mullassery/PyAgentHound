from datetime import datetime, timedelta, timezone

import pytest

from pyagenthound.sdk.models import Span, SpanType, Trace


def test_trace_json_roundtrip():
    trace = Trace(
        name="t",
        spans=[
            Span(
                trace_id="abc",
                name="s",
                span_type=SpanType.LLM,
                attributes={"k": "v"},
            )
        ],
    )
    raw = trace.model_dump_json()
    restored = Trace.model_validate_json(raw)

    assert restored.name == "t"
    assert restored.spans[0].span_type == SpanType.LLM
    assert restored.spans[0].attributes == {"k": "v"}


def test_span_duration_ms():
    start = datetime.now(timezone.utc)
    span = Span(
        trace_id="t", name="s", start_time=start, end_time=start + timedelta(milliseconds=250)
    )
    assert span.duration_ms == pytest.approx(250, abs=1)


def test_span_duration_ms_none_when_not_ended():
    span = Span(trace_id="t", name="s")
    assert span.duration_ms is None


def test_span_type_defaults_to_custom():
    span = Span(trace_id="t", name="s")
    assert span.span_type == SpanType.CUSTOM
