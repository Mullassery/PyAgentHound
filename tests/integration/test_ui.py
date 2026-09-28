from fastapi.testclient import TestClient

from pyagenthound.api.app import create_app
from pyagenthound.sdk.models import Span, SpanStatus, SpanType, Trace


def _client(tmp_path) -> TestClient:
    app = create_app(tmp_path / "api.db")
    return TestClient(app)


def test_requests_list_empty_state(tmp_path):
    resp = _client(tmp_path).get("/")
    assert resp.status_code == 200
    assert "No traces captured yet" in resp.text


def test_requests_list_shows_traces(tmp_path):
    client = _client(tmp_path)
    trace = Trace(name="checkout", status=SpanStatus.OK)
    client.post("/api/traces", json=trace.model_dump(mode="json"))

    resp = client.get("/")

    assert resp.status_code == 200
    assert "checkout" in resp.text
    assert trace.trace_id in resp.text


def test_requests_list_name_filter(tmp_path):
    client = _client(tmp_path)
    client.post("/api/traces", json=Trace(name="checkout").model_dump(mode="json"))
    client.post("/api/traces", json=Trace(name="support").model_dump(mode="json"))

    resp = client.get("/", params={"name": "checkout"})

    assert "checkout" in resp.text
    assert "support" not in resp.text


def test_request_detail_renders_findings_and_root_cause(tmp_path):
    client = _client(tmp_path)
    trace = Trace(name="req")
    trace.spans.append(
        Span(
            trace_id=trace.trace_id,
            name="retrieval",
            span_type=SpanType.RETRIEVAL,
            attributes={"documents": []},
        )
    )
    client.post("/api/traces", json=trace.model_dump(mode="json"))

    resp = client.get(f"/requests/{trace.trace_id}")

    assert resp.status_code == 200
    assert "Retrieval returned no documents" in resp.text
    assert "Likely cause" in resp.text
    assert 'data-trace-id="' + trace.trace_id + '"' in resp.text


def test_request_detail_404(tmp_path):
    resp = _client(tmp_path).get("/requests/does-not-exist")
    assert resp.status_code == 404


def test_replay_from_ui_redirects_to_replayed_trace(tmp_path):
    client = _client(tmp_path)
    trace = Trace(name="req")
    trace.spans.append(
        Span(
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
    )
    client.post("/api/traces", json=trace.model_dump(mode="json"))

    resp = client.post(
        f"/requests/{trace.trace_id}/replay",
        data={"override": 'retrieval.documents=[{"id": "b", "date": "2026-01-01"}]'},
        follow_redirects=False,
    )

    assert resp.status_code == 303
    replayed_url = resp.headers["location"]
    assert replayed_url.startswith("/requests/")
    assert replayed_url != f"/requests/{trace.trace_id}"

    follow = client.get(replayed_url)
    assert follow.status_code == 200
    assert "Replayed from" in follow.text


def test_replay_from_ui_unsafe_override_redirects_with_error(tmp_path):
    client = _client(tmp_path)
    trace = Trace(name="req")
    trace.spans.append(Span(trace_id=trace.trace_id, name="tool", span_type=SpanType.TOOL))
    client.post("/api/traces", json=trace.model_dump(mode="json"))

    resp = client.post(
        f"/requests/{trace.trace_id}/replay",
        data={"override": "tool.args={}"},
        follow_redirects=False,
    )

    assert resp.status_code == 303
    assert resp.headers["location"].startswith(f"/requests/{trace.trace_id}?replay_error=")
