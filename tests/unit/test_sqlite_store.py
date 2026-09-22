from pyagenthound.sdk.models import Event, Span, SpanStatus, SpanType, Trace
from pyagenthound.storage.sqlite_store import SQLiteTraceStore


def test_save_and_get_trace_roundtrip(tmp_path):
    store = SQLiteTraceStore(tmp_path / "t.db")
    trace = Trace(name="t", tags=["x"], metadata={"env": "test"})
    span = Span(
        trace_id=trace.trace_id,
        name="s",
        span_type=SpanType.RETRIEVAL,
        attributes={"query": "q"},
        events=[Event(name="e", attributes={"a": 1})],
        input={"q": "q"},
        output=["doc1"],
    )
    trace.spans.append(span)
    trace.end_time = trace.start_time
    trace.status = SpanStatus.OK
    store.save_trace(trace)

    got = store.get_trace(trace.trace_id)
    assert got is not None
    assert got.name == "t"
    assert got.tags == ["x"]
    assert got.metadata == {"env": "test"}
    assert len(got.spans) == 1
    assert got.spans[0].attributes == {"query": "q"}
    assert got.spans[0].events[0].name == "e"
    assert got.spans[0].input == {"q": "q"}
    assert got.spans[0].output == ["doc1"]


def test_get_trace_missing_returns_none(tmp_path):
    store = SQLiteTraceStore(tmp_path / "t.db")
    assert store.get_trace("nonexistent") is None


def test_list_traces_pagination_and_status_filter(tmp_path):
    store = SQLiteTraceStore(tmp_path / "t.db")
    for i in range(3):
        t = Trace(name=f"t{i}", status=SpanStatus.OK if i < 2 else SpanStatus.ERROR)
        store.save_trace(t)

    assert len(store.list_traces(limit=10)) == 3
    assert len(store.list_traces(status=SpanStatus.OK)) == 2
    assert len(store.list_traces(limit=1)) == 1


def test_save_trace_upsert_updates_existing(tmp_path):
    store = SQLiteTraceStore(tmp_path / "t.db")
    trace = Trace(name="t")
    store.save_trace(trace)

    trace.status = SpanStatus.OK
    trace.end_time = trace.start_time
    store.save_trace(trace)

    got = store.get_trace(trace.trace_id)
    assert got is not None
    assert got.status == SpanStatus.OK
