"""Execution signature extraction. See docs/architecture.md section 6.

A signature is a lightweight, comparable summary of what a trace actually did — the
fields the product spec's historical-baseline section (6.8) names as worth watching
for drift between executions.
"""

from __future__ import annotations

from pydantic import BaseModel, Field

from pyagenthound.sdk.models import SpanType, Trace


class ExecutionSignature(BaseModel):
    trace_id: str
    model: str | None = None
    prompt_version: str | None = None
    retriever: str | None = None
    tools: list[str] = Field(default_factory=list)
    latency_ms: float | None = None
    input_tokens: int | None = None
    output_tokens: int | None = None
    execution_path: list[str] = Field(default_factory=list)

    @property
    def total_tokens(self) -> int | None:
        if self.input_tokens is None and self.output_tokens is None:
            return None
        return (self.input_tokens or 0) + (self.output_tokens or 0)


def extract_signature(trace: Trace) -> ExecutionSignature:
    model: str | None = None
    prompt_version: str | None = None
    retriever: str | None = None
    tools: list[str] = []
    input_tokens: int | None = None
    output_tokens: int | None = None

    ordered = sorted(trace.spans, key=lambda s: s.start_time)
    for span in ordered:
        if span.span_type == SpanType.LLM:
            model = span.attributes.get("model", model)
            prompt_version = span.attributes.get("prompt_version", prompt_version)
            tokens_in = span.attributes.get("input_tokens")
            if isinstance(tokens_in, int):
                input_tokens = (input_tokens or 0) + tokens_in
            tokens_out = span.attributes.get("output_tokens")
            if isinstance(tokens_out, int):
                output_tokens = (output_tokens or 0) + tokens_out
        elif span.span_type == SpanType.RETRIEVAL:
            retriever = span.attributes.get("retriever", retriever)
        elif span.span_type in (SpanType.TOOL, SpanType.MCP):
            tools.append(span.name)

    return ExecutionSignature(
        trace_id=trace.trace_id,
        model=model,
        prompt_version=prompt_version,
        retriever=retriever,
        tools=tools,
        latency_ms=trace.duration_ms,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        execution_path=[span.span_type.value for span in ordered],
    )
