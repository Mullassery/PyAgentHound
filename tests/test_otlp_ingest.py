"""OTLP JSON -> Trace mapping tests. No OpenTelemetry SDK or network needed."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from pyagenthound.api.app import create_app
from pyagenthound.ingest.otlp import otlp_json_to_traces
from pyagenthound.sdk.models import SpanStatus, SpanType

NS = 1_700_000_000_000_000_000


def _payload():
    return {
        "resourceSpans": [
            {
                "resource": {
                    "attributes": [
                        {"key": "service.name", "value": {"stringValue": "research-agent"}}
                    ]
                },
                "scopeSpans": [
                    {
                        "spans": [
                            {
                                "traceId": "a" * 32,
                                "spanId": "b" * 16,
                                "name": "llm.chat",
                                "startTimeUnixNano": str(NS),
                                "endTimeUnixNano": str(NS + 2_000_000_000),
                                "status": {"code": 1},
                                "attributes": [
                                    {
                                        "key": "openinference.span.kind",
                                        "value": {"stringValue": "LLM"},
                                    },
                                    {
                                        "key": "gen_ai.request.model",
                                        "value": {"stringValue": "gpt-4o"},
                                    },
                                    {
                                        "key": "output.value",
                                        "value": {"stringValue": "done"},
                                    },
                                ],
                            },
                            {
                                "traceId": "a" * 32,
                                "spanId": "c" * 16,
                                "parentSpanId": "b" * 16,
                                "name": "retriever.search",
                                "startTimeUnixNano": str(NS + 100_000_000),
                                "endTimeUnixNano": str(NS + 500_000_000),
                                "status": {"code": 2, "message": "index unavailable"},
                                "attributes": [
                                    {
                                        "key": "openinference.span.kind",
                                        "value": {"stringValue": "RETRIEVER"},
                                    }
                                ],
                            },
                        ]
                    }
                ],
            }
        ]
    }


def test_otlp_json_maps_trace_and_span_types():
    traces = otlp_json_to_traces(_payload())
    assert len(traces) == 1
    trace = traces[0]
    assert trace.name == "research-agent"
    assert len(trace.spans) == 2
    assert {s.span_type for s in trace.spans} == {SpanType.LLM, SpanType.RETRIEVAL}
    assert trace.spans[0].output == "done"
    assert trace.spans[0].attributes["gen_ai.request.model"] == "gpt-4o"
    assert trace.spans[1].status is SpanStatus.ERROR
    assert trace.status is SpanStatus.ERROR


def test_otlp_http_endpoint_persists_traces(tmp_path):
    app = create_app(tmp_path / "traces.db")
    client = TestClient(app)
    response = client.post(
        "/v1/traces",
        json=_payload(),
        headers={"content-type": "application/json"},
    )
    assert response.status_code == 200, response.text
    traces = client.get("/api/traces").json()
    assert len(traces) == 1
    assert traces[0]["name"] == "research-agent"


def test_otlp_http_rejects_unknown_content_type(tmp_path):
    app = create_app(tmp_path / "traces.db")
    client = TestClient(app)
    response = client.post("/v1/traces", content=b"{}", headers={"content-type": "text/plain"})
    assert response.status_code == 415


def test_otlp_protobuf_roundtrip():
    pytest.importorskip("opentelemetry.proto")
    from opentelemetry.proto.collector.trace.v1.trace_service_pb2 import (
        ExportTraceServiceRequest,
    )

    # Build the same shape as the JSON fixture through the protobuf API.
    req = ExportTraceServiceRequest()
    rs = req.resource_spans.add()
    ss = rs.scope_spans.add()
    span = ss.spans.add()
    span.trace_id = b"a" * 16
    span.span_id = b"b" * 8
    span.name = "llm.chat"
    span.start_time_unix_nano = NS
    span.end_time_unix_nano = NS + 1_000_000
    attr = span.attributes.add()
    attr.key = "gen_ai.usage.input_tokens"
    attr.value.int_value = 2
    from pyagenthound.ingest.otlp import otlp_json_to_traces, parse_otlp_protobuf

    payload = parse_otlp_protobuf(req.SerializeToString())
    traces = otlp_json_to_traces(payload)
    assert len(traces) == 1
    assert traces[0].spans[0].name == "llm.chat"
