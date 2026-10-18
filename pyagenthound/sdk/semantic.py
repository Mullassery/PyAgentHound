"""Mapping from PyAgentHound's span model to OpenTelemetry GenAI semantic
conventions and OpenInference attribute names (RECHECK-037).

PyAgentHound's own attributes are deliberately free-form: instrumentation can set
whatever it likes and analyzers pattern-match on it. That is useful for the
analyzer, but it means a trace exported to an Off-the-shelf OTel backend (or an
OpenInference viewer such as Arize Phoenix) has no semantic meaning attached.

This module adds that meaning *without* changing the storage model: it derives
``gen_ai.*`` and ``openinference.*`` attributes from a :class:`Span` and the
aliases callers commonly use, never overwriting an attribute the caller already
set. The original attributes are left untouched, so existing analyzers keep
working.

See:
- OTel GenAI semantic conventions: https://opentelemetry.io/docs/specs/semconv/gen-ai/
- OpenInference: https://github.com/Arize-ai/openinference
"""

from __future__ import annotations

import json
from typing import Any

from pyagenthound.sdk.models import Span, SpanType

# OpenInference span kinds. PyAgentHound's finer-grained SpanType collapses onto
# these; the original SpanType stays available on the Span itself.
SPAN_TYPE_TO_OPENINFERENCE_KIND: dict[SpanType, str] = {
    SpanType.AGENT: "AGENT",
    SpanType.LLM: "LLM",
    SpanType.RETRIEVAL: "RETRIEVER",
    SpanType.EMBEDDING: "EMBEDDING",
    SpanType.RERANKING: "RERANKER",
    SpanType.TOOL: "TOOL",
    SpanType.MCP: "TOOL",
    SpanType.API: "CHAIN",
    SpanType.DATABASE: "CHAIN",
    SpanType.VECTOR_DB: "RETRIEVER",
    SpanType.PROMPT: "CHAIN",
    SpanType.MEMORY: "RETRIEVER",
    SpanType.GUARDRAIL: "GUARDRAIL",
    SpanType.EVALUATION: "EVALUATOR",
    SpanType.CUSTOM: "CHAIN",
}

# OTel GenAI `gen_ai.operation.name` values for the span types that have one.
SPAN_TYPE_TO_OPERATION_NAME: dict[SpanType, str] = {
    SpanType.LLM: "chat",
    SpanType.EMBEDDING: "embeddings",
    SpanType.TOOL: "execute_tool",
    SpanType.MCP: "execute_tool",
    SpanType.RETRIEVAL: "retrieval",
    SpanType.VECTOR_DB: "retrieval",
    SpanType.RERANKING: "rerank",
}

# Caller aliases we accept as the source of each semantic value, in priority
# order. The canonical key is always checked first.
_SYSTEM_ALIASES = ("gen_ai.system", "gen_ai.provider.name", "system", "provider", "llm.system")
_REQUEST_MODEL_ALIASES = ("gen_ai.request.model", "model", "model_name", "llm.model_name")
_RESPONSE_MODEL_ALIASES = ("gen_ai.response.model", "response_model")
_OPERATION_ALIASES = ("gen_ai.operation.name", "operation", "operation_name")
_INPUT_TOKEN_ALIASES = (
    "gen_ai.usage.input_tokens",
    "input_tokens",
    "prompt_tokens",
    "llm.token_count.prompt",
)
_OUTPUT_TOKEN_ALIASES = (
    "gen_ai.usage.output_tokens",
    "output_tokens",
    "completion_tokens",
    "llm.token_count.completion",
)


def _first(attributes: dict[str, Any], keys: tuple[str, ...]) -> Any:
    for key in keys:
        if key in attributes and attributes[key] is not None:
            return attributes[key]
    return None


def _as_int(value: Any) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _jsonify(value: Any) -> str:
    return value if isinstance(value, str) else json.dumps(value, default=str)


def span_semantic_attributes(span: Span) -> dict[str, Any]:
    """Return ``span.attributes`` plus derived GenAI/OpenInference convention keys.

    The input dict is not mutated. A derived key is only added when the caller
    hasn't already set it, so explicit instrumentation always wins.
    """
    attributes: dict[str, Any] = dict(span.attributes)

    def setdefault(key: str, value: Any) -> None:
        if value is not None and key not in attributes:
            attributes[key] = value

    setdefault(
        "openinference.span.kind",
        SPAN_TYPE_TO_OPENINFERENCE_KIND.get(span.span_type, "CHAIN"),
    )
    setdefault(
        "gen_ai.operation.name",
        _first(attributes, _OPERATION_ALIASES)
        or SPAN_TYPE_TO_OPERATION_NAME.get(span.span_type),
    )
    setdefault("gen_ai.system", _first(attributes, _SYSTEM_ALIASES))

    request_model = _first(attributes, _REQUEST_MODEL_ALIASES)
    setdefault("gen_ai.request.model", request_model)
    setdefault("llm.model_name", request_model)
    setdefault("gen_ai.response.model", _first(attributes, _RESPONSE_MODEL_ALIASES))

    input_tokens = _as_int(_first(attributes, _INPUT_TOKEN_ALIASES))
    output_tokens = _as_int(_first(attributes, _OUTPUT_TOKEN_ALIASES))
    setdefault("gen_ai.usage.input_tokens", input_tokens)
    setdefault("gen_ai.usage.output_tokens", output_tokens)
    setdefault("llm.token_count.prompt", input_tokens)
    setdefault("llm.token_count.completion", output_tokens)
    if input_tokens is not None and output_tokens is not None:
        setdefault("llm.token_count.total", input_tokens + output_tokens)

    if span.input is not None:
        setdefault("input.value", _jsonify(span.input))
    if span.output is not None:
        setdefault("output.value", _jsonify(span.output))

    return attributes


def span_to_otel(span: Span) -> dict[str, Any]:
    """A transport-neutral OTLP-ish view of a span, with semantic attributes.

    Deliberately not an ``opentelemetry.sdk`` object: this keeps the core SDK
    dependency-free, while giving exporters everything they need to build one.
    """
    return {
        "name": span.name,
        "trace_id": span.trace_id,
        "span_id": span.span_id,
        "parent_span_id": span.parent_span_id,
        "start_time": span.start_time.isoformat(),
        "end_time": span.end_time.isoformat() if span.end_time else None,
        "status": span.status.value,
        "attributes": span_semantic_attributes(span),
    }
