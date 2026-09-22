import pytest

from pyagenthound.sdk.client import AgentHound
from pyagenthound.sdk.models import SpanStatus, SpanType
from pyagenthound.storage.sqlite_store import SQLiteTraceStore


def test_manual_trace_and_span(tmp_path):
    db_path = tmp_path / "traces.db"
    hound = AgentHound(db_path=db_path)

    with hound.trace("my-trace") as trace:
        with trace.span("step1", span_type=SpanType.LLM) as span:
            span.set_attribute("model", "gpt-4o")
            span.set_output("hello")

    assert trace.trace.status == SpanStatus.OK

    store = SQLiteTraceStore(db_path)
    saved = store.get_trace(trace.trace.trace_id)
    assert saved is not None
    assert saved.name == "my-trace"
    assert len(saved.spans) == 1
    assert saved.spans[0].attributes["model"] == "gpt-4o"
    assert saved.spans[0].output == "hello"


def test_nested_spans_set_parent(tmp_path):
    hound = AgentHound(db_path=tmp_path / "t.db")

    with hound.trace("t") as trace:
        with trace.span("outer"):
            with trace.span("inner"):
                pass

    spans = {s.name: s for s in trace.trace.spans}
    assert spans["inner"].parent_span_id == spans["outer"].span_id


def test_span_records_error(tmp_path):
    hound = AgentHound(db_path=tmp_path / "t.db")

    with pytest.raises(ValueError):
        with hound.trace("t") as trace:
            with trace.span("boom"):
                raise ValueError("bad")

    span = trace.trace.spans[0]
    assert span.status == SpanStatus.ERROR
    assert span.error is not None
    assert span.error.type == "ValueError"
    assert trace.trace.status == SpanStatus.ERROR


def test_trace_and_span_decorators(tmp_path):
    db_path = tmp_path / "t.db"
    hound = AgentHound(db_path=db_path)

    @hound.span("decorated-span", span_type=SpanType.TOOL)
    def inner() -> None:
        pass

    @hound.trace("decorated-trace")
    def outer() -> None:
        inner()

    outer()

    store = SQLiteTraceStore(db_path)
    traces = store.list_traces()
    assert len(traces) == 1
    assert traces[0].name == "decorated-trace"

    full = store.get_trace(traces[0].trace_id)
    assert full is not None
    assert full.spans[0].name == "decorated-span"
    assert full.spans[0].span_type == SpanType.TOOL


def test_span_decorator_requires_active_trace(tmp_path):
    hound = AgentHound(db_path=tmp_path / "t.db")

    @hound.span("x")
    def f() -> None:
        pass

    with pytest.raises(RuntimeError):
        f()
