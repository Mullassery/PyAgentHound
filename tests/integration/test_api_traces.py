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


def test_get_trace_graph(tmp_path):
    client = _client(tmp_path)

    trace = Trace(name="req")
    trace.spans.append(
        Span(
            trace_id=trace.trace_id,
            name="retrieval",
            span_type=SpanType.RETRIEVAL,
            attributes={"documents": ["policy-2024"]},
        )
    )
    client.post("/api/traces", json=trace.model_dump(mode="json"))

    resp = client.get(f"/api/traces/{trace.trace_id}/graph")
    assert resp.status_code == 200
    body = resp.json()
    assert body["trace_id"] == trace.trace_id
    node_types = {n["type"] for n in body["nodes"]}
    assert "DOCUMENT" in node_types
    relationships = {e["relationship"] for e in body["edges"]}
    assert "RETRIEVES" in relationships
    assert "PARENT" in relationships


def test_get_trace_graph_404(tmp_path):
    resp = _client(tmp_path).get("/api/traces/does-not-exist/graph")
    assert resp.status_code == 404


def test_analyze_trace_returns_findings(tmp_path):
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

    resp = client.post(f"/api/traces/{trace.trace_id}/analyze")
    assert resp.status_code == 200
    findings = resp.json()
    assert len(findings) == 1
    assert findings[0]["rule_id"] == "empty_retrieval"


def test_analyze_trace_404(tmp_path):
    resp = _client(tmp_path).post("/api/traces/does-not-exist/analyze")
    assert resp.status_code == 404


def test_root_cause_returns_ranked_hypotheses(tmp_path):
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

    resp = client.get(f"/api/traces/{trace.trace_id}/root-cause")
    assert resp.status_code == 200
    hypotheses = resp.json()
    assert len(hypotheses) == 1
    assert hypotheses[0]["label"] == "likely_cause"
    assert hypotheses[0]["confidence_components"]["temporal_correlation"] is None


def test_root_cause_404(tmp_path):
    resp = _client(tmp_path).get("/api/traces/does-not-exist/root-cause")
    assert resp.status_code == 404


def test_list_traces_name_filter(tmp_path):
    client = _client(tmp_path)
    client.post("/api/traces", json=Trace(name="checkout").model_dump(mode="json"))
    client.post("/api/traces", json=Trace(name="support").model_dump(mode="json"))

    resp = client.get("/api/traces", params={"name": "checkout"})
    assert resp.status_code == 200
    body = resp.json()
    assert len(body) == 1
    assert body[0]["name"] == "checkout"


def _post_trace(client: TestClient, name: str, status: SpanStatus, model: str) -> Trace:
    trace = Trace(name=name, status=status)
    trace.spans.append(
        Span(
            trace_id=trace.trace_id,
            name="llm",
            span_type=SpanType.LLM,
            attributes={"model": model},
        )
    )
    client.post("/api/traces", json=trace.model_dump(mode="json"))
    return trace


def test_analyze_includes_baseline_findings_when_available(tmp_path):
    client = _client(tmp_path)
    _post_trace(client, "checkout", SpanStatus.OK, "gpt-4o")
    current = _post_trace(client, "checkout", SpanStatus.ERROR, "gpt-4-turbo")

    resp = client.post(f"/api/traces/{current.trace_id}/analyze")

    assert resp.status_code == 200
    findings = resp.json()
    assert any(f["rule_id"] == "baseline_model_changed" for f in findings)


def test_root_cause_sets_temporal_correlation_from_baseline(tmp_path):
    client = _client(tmp_path)
    _post_trace(client, "checkout", SpanStatus.OK, "gpt-4o")
    current = _post_trace(client, "checkout", SpanStatus.ERROR, "gpt-4-turbo")

    resp = client.get(f"/api/traces/{current.trace_id}/root-cause")

    assert resp.status_code == 200
    hypotheses = resp.json()
    model_change = next(h for h in hypotheses if h["rule_id"] == "baseline_model_changed")
    assert model_change["confidence_components"]["temporal_correlation"] == 1.0


def test_replay_resolves_finding(tmp_path):
    client = _client(tmp_path)

    trace = Trace(name="req")
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
    trace.spans.append(retrieval)
    client.post("/api/traces", json=trace.model_dump(mode="json"))

    resp = client.post(
        f"/api/traces/{trace.trace_id}/replay",
        json={"overrides": {retrieval.span_id: {"documents": [{"id": "b", "date": "2026-01-01"}]}}},
    )

    assert resp.status_code == 200
    body = resp.json()
    assert "stale_retrieval_documents" in body["resolved_rule_ids"]

    replayed = client.get(f"/api/traces/{body['replayed_trace_id']}")
    assert replayed.status_code == 200


def test_replay_requires_confirmation_for_unsafe_override(tmp_path):
    client = _client(tmp_path)

    trace = Trace(name="req")
    tool = Span(trace_id=trace.trace_id, name="tool", span_type=SpanType.TOOL)
    trace.spans.append(tool)
    client.post("/api/traces", json=trace.model_dump(mode="json"))

    resp = client.post(
        f"/api/traces/{trace.trace_id}/replay",
        json={"overrides": {tool.span_id: {"args": {}}}},
    )
    assert resp.status_code == 409

    resp = client.post(
        f"/api/traces/{trace.trace_id}/replay",
        json={"overrides": {tool.span_id: {"args": {}}}, "allow_unsafe": True},
    )
    assert resp.status_code == 200


def test_replay_404(tmp_path):
    resp = _client(tmp_path).post("/api/traces/does-not-exist/replay", json={"overrides": {}})
    assert resp.status_code == 404
