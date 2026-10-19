"""OTLP ingest: OpenTelemetry traces -> PyAgentHound traces.

Supports OTLP/HTTP JSON natively and protobuf when the optional
``opentelemetry-proto`` package is installed. It maps OpenInference and
OpenTelemetry GenAI attributes onto PyAgentHound's span model so existing
instrumented agents can be debugged without changing their instrumentation.
"""

from __future__ import annotations

import logging
from collections.abc import Iterable
from datetime import datetime, timezone
from typing import Any

from pyagenthound.sdk.models import Event, Span, SpanError, SpanStatus, SpanType, Trace

logger = logging.getLogger(__name__)


class OTLPUnavailable(RuntimeError):
    """Raised when protobuf OTLP is requested without opentelemetry-proto."""


def _ns_to_datetime(value: Any) -> datetime:
    try:
        ns = int(value)
    except (TypeError, ValueError):
        return datetime.now(timezone.utc)
    # OTLP uses nanoseconds since Unix epoch.
    return datetime.fromtimestamp(ns / 1_000_000_000, tz=timezone.utc)


def _attr_value(value: dict[str, Any]) -> Any:
    if not isinstance(value, dict):
        return value
    for key in (
        "stringValue",
        "string_value",
        "intValue",
        "int_value",
        "doubleValue",
        "double_value",
        "boolValue",
        "bool_value",
    ):
        if key in value:
            return value[key]
    if "arrayValue" in value or "array_value" in value:
        arr = value.get("arrayValue") or value.get("array_value") or {}
        return [_attr_value(v) for v in (arr.get("values") or [])]
    if "kvlistValue" in value or "kvlist_value" in value:
        kv = value.get("kvlistValue") or value.get("kvlist_value") or {}
        return {
            item.get("key"): _attr_value(item.get("value") or {})
            for item in (kv.get("values") or [])
        }
    return value


def _attrs(items: Iterable[dict[str, Any]] | None) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for item in items or []:
        key = item.get("key")
        if key:
            result[str(key)] = _attr_value(item.get("value") or {})
    return result


def _span_type(attrs: dict[str, Any], name: str) -> SpanType:
    raw = (
        attrs.get("openinference.span.kind")
        or attrs.get("gen_ai.operation.name")
        or attrs.get("llm.request.type")
        or attrs.get("span.type")
        or attrs.get("type")
    )
    value = str(raw or "").upper()
    lowered = name.lower()
    mapping = {
        "LLM": SpanType.LLM,
        "CHAT": SpanType.LLM,
        "COMPLETION": SpanType.LLM,
        "TOOL": SpanType.TOOL,
        "RETRIEVER": SpanType.RETRIEVAL,
        "RETRIEVAL": SpanType.RETRIEVAL,
        "EMBEDDING": SpanType.EMBEDDING,
        "RERANKER": SpanType.RERANKING,
        "RERANKING": SpanType.RERANKING,
        "AGENT": SpanType.AGENT,
        "CHAIN": SpanType.AGENT,
        "MCP": SpanType.MCP,
        "GUARDRAIL": SpanType.GUARDRAIL,
        "EVALUATOR": SpanType.EVALUATION,
    }
    if value in mapping:
        return mapping[value]
    if any(token in lowered for token in ("llm", "chat", "completion")):
        return SpanType.LLM
    if any(token in lowered for token in ("tool", "function")):
        return SpanType.TOOL
    if any(token in lowered for token in ("retriev", "search", "vector")):
        return SpanType.RETRIEVAL
    if "embed" in lowered:
        return SpanType.EMBEDDING
    return SpanType.CUSTOM


def _input_output(attrs: dict[str, Any]) -> tuple[Any, Any]:
    input_value = (
        attrs.get("input.value")
        or attrs.get("gen_ai.prompt")
        or attrs.get("llm.input_messages")
        or attrs.get("openinference.input.value")
    )
    output_value = (
        attrs.get("output.value")
        or attrs.get("gen_ai.completion")
        or attrs.get("llm.output_messages")
        or attrs.get("openinference.output.value")
    )
    return input_value, output_value


def _span_from_otlp(span: dict[str, Any], trace_id: str) -> Span:
    attrs = _attrs(span.get("attributes"))
    status_data = span.get("status") or {}
    status_code = status_data.get("code")
    if status_code in (2, "STATUS_CODE_ERROR", "ERROR"):
        status = SpanStatus.ERROR
    elif status_code in (1, "STATUS_CODE_OK", "OK"):
        status = SpanStatus.OK
    else:
        status = SpanStatus.UNSET

    events = []
    for event in span.get("events") or []:
        events.append(
            Event(
                name=str(event.get("name") or "event"),
                timestamp=_ns_to_datetime(event.get("timeUnixNano") or event.get("time_unix_nano")),
                attributes=_attrs(event.get("attributes")),
            )
        )

    error = None
    message = status_data.get("message")
    if status is SpanStatus.ERROR:
        error = SpanError(type="OTLPError", message=str(message or "OTLP span reported an error"))

    input_value, output_value = _input_output(attrs)
    return Span(
        span_id=str(span.get("spanId") or span.get("span_id") or ""),
        trace_id=trace_id,
        parent_span_id=span.get("parentSpanId") or span.get("parent_span_id") or None,
        name=str(span.get("name") or "span"),
        span_type=_span_type(attrs, str(span.get("name") or "")),
        start_time=_ns_to_datetime(
            span.get("startTimeUnixNano") or span.get("start_time_unix_nano")
        ),
        end_time=(
            _ns_to_datetime(span.get("endTimeUnixNano") or span.get("end_time_unix_nano"))
            if (span.get("endTimeUnixNano") or span.get("end_time_unix_nano"))
            else None
        ),
        status=status,
        status_message=message,
        attributes=attrs,
        events=events,
        input=input_value,
        output=output_value,
        error=error,
    )


def otlp_json_to_traces(payload: dict[str, Any]) -> list[Trace]:
    """Convert an OTLP/HTTP JSON ExportTraceServiceRequest into traces."""
    traces: dict[str, Trace] = {}
    for resource_span in payload.get("resourceSpans") or payload.get("resource_spans") or []:
        resource_attrs = _attrs((resource_span.get("resource") or {}).get("attributes"))
        service_name = (
            resource_attrs.get("service.name") or resource_attrs.get("agent.name") or "otlp"
        )
        for scope_span in resource_span.get("scopeSpans") or resource_span.get("scope_spans") or []:
            for raw_span in scope_span.get("spans") or []:
                trace_id = str(raw_span.get("traceId") or raw_span.get("trace_id") or "")
                if not trace_id:
                    continue
                span = _span_from_otlp(raw_span, trace_id)
                trace = traces.get(trace_id)
                if trace is None:
                    trace = Trace(
                        trace_id=trace_id,
                        name=str(service_name),
                        metadata={"ingest": "otlp", "resource": resource_attrs},
                    )
                    traces[trace_id] = trace
                trace.spans.append(span)
                if span.start_time < trace.start_time:
                    trace.start_time = span.start_time
                if span.end_time and (trace.end_time is None or span.end_time > trace.end_time):
                    trace.end_time = span.end_time
                if span.status is SpanStatus.ERROR:
                    trace.status = SpanStatus.ERROR

    for trace in traces.values():
        if trace.end_time is None and trace.spans:
            ends = [s.end_time for s in trace.spans if s.end_time is not None]
            if ends:
                trace.end_time = max(ends)
        if trace.status is not SpanStatus.ERROR:
            trace.status = SpanStatus.OK
    return list(traces.values())


def parse_otlp_protobuf(body: bytes) -> dict[str, Any]:
    """Decode OTLP protobuf into the JSON-shaped dict used above."""
    try:
        from google.protobuf.json_format import MessageToDict
        from opentelemetry.proto.collector.trace.v1.trace_service_pb2 import (
            ExportTraceServiceRequest,
        )
    except ImportError as exc:  # pragma: no cover - optional dependency
        raise OTLPUnavailable(
            "Protobuf OTLP requires the optional dependency. Install with "
            '`pip install "pyagenthound[otlp]"`. JSON OTLP works without it.'
        ) from exc

    request = ExportTraceServiceRequest()
    request.ParseFromString(body)
    return MessageToDict(request, preserving_proto_field_name=False)


__all__ = ["OTLPUnavailable", "otlp_json_to_traces", "parse_otlp_protobuf"]
