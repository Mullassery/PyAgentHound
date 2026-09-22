from fastapi.testclient import TestClient

from pyagenthound.api.app import create_app
from pyagenthound.sdk.models import Span, SpanStatus, SpanType, Trace


def _client(tmp_path) -> TestClient:
    app = create_app(tmp_path / "api.db")
    return TestClient(app)


def test_health(tmp_path):
    resp = _client(tmp_path).get("/health")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}


def test_create_list_get_trace(tmp_path):
    client = _client(tmp_path)

    trace = Trace(name="req", status=SpanStatus.OK)
    trace.spans.append(Span(trace_id=trace.trace_id, name="s", span_type=SpanType.LLM))
    payload = trace.model_dump(mode="json")

    resp = client.post("/api/traces", json=payload)
    assert resp.status_code == 201

    resp = client.get("/api/traces")
    assert resp.status_code == 200
    body = resp.json()
    assert len(body) == 1
    assert body[0]["trace_id"] == trace.trace_id
    assert body[0]["span_count"] == 1

    resp = client.get(f"/api/traces/{trace.trace_id}")
    assert resp.status_code == 200
    got = resp.json()
    assert got["name"] == "req"
    assert len(got["spans"]) == 1


def test_get_trace_404(tmp_path):
    resp = _client(tmp_path).get("/api/traces/does-not-exist")
    assert resp.status_code == 404


def test_list_traces_status_filter(tmp_path):
    client = _client(tmp_path)
    client.post("/api/traces", json=Trace(name="ok", status=SpanStatus.OK).model_dump(mode="json"))
    client.post(
        "/api/traces", json=Trace(name="err", status=SpanStatus.ERROR).model_dump(mode="json")
    )

    resp = client.get("/api/traces", params={"status": "ERROR"})
    assert resp.status_code == 200
    body = resp.json()
    assert len(body) == 1
    assert body[0]["name"] == "err"
