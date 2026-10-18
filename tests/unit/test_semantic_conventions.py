from pyagenthound.sdk.models import Span, SpanStatus, SpanType
from pyagenthound.sdk.semantic import span_semantic_attributes, span_to_otel


def _span(**kwargs):
    return Span(trace_id="t" * 32, name="s", **kwargs)


def test_llm_span_gets_genai_and_openinference_attributes():
    span = _span(
        span_type=SpanType.LLM,
        attributes={
            "model": "gpt-4o",
            "provider": "openai",
            "input_tokens": 11,
            "output_tokens": 7,
        },
    )

    attrs = span_semantic_attributes(span)

    assert attrs["openinference.span.kind"] == "LLM"
    assert attrs["gen_ai.operation.name"] == "chat"
    assert attrs["gen_ai.system"] == "openai"
    assert attrs["gen_ai.request.model"] == "gpt-4o"
    assert attrs["llm.model_name"] == "gpt-4o"
    assert attrs["gen_ai.usage.input_tokens"] == 11
    assert attrs["gen_ai.usage.output_tokens"] == 7
    assert attrs["llm.token_count.prompt"] == 11
    assert attrs["llm.token_count.completion"] == 7
    assert attrs["llm.token_count.total"] == 18


def test_explicit_canonical_keys_are_not_overwritten():
    span = _span(
        span_type=SpanType.LLM,
        attributes={
            "model": "alias-model",
            "gen_ai.request.model": "explicit-model",
            "input_tokens": 99,
            "gen_ai.usage.input_tokens": 5,
        },
    )

    attrs = span_semantic_attributes(span)

    assert attrs["gen_ai.request.model"] == "explicit-model"
    assert attrs["llm.model_name"] == "explicit-model"
    assert attrs["gen_ai.usage.input_tokens"] == 5


def test_tool_span_kind_and_operation():
    attrs = span_semantic_attributes(_span(span_type=SpanType.TOOL))
    assert attrs["openinference.span.kind"] == "TOOL"
    assert attrs["gen_ai.operation.name"] == "execute_tool"


def test_database_span_has_no_operation_name():
    attrs = span_semantic_attributes(_span(span_type=SpanType.DATABASE))
    assert attrs["openinference.span.kind"] == "CHAIN"
    assert "gen_ai.operation.name" not in attrs


def test_input_and_output_become_values():
    span = _span(input={"question": "hi"}, output="answer")
    attrs = span_semantic_attributes(span)
    assert attrs["input.value"] == '{"question": "hi"}'
    assert attrs["output.value"] == "answer"


def test_source_attributes_are_not_mutated_and_method_matches():
    span = _span(span_type=SpanType.LLM, attributes={"model": "m"})
    attrs = span_semantic_attributes(span)

    assert span.attributes == {"model": "m"}
    assert span.semantic_attributes() == attrs


def test_span_to_otel_view():
    span = _span(span_type=SpanType.LLM, attributes={"model": "m"}, status=SpanStatus.OK)

    otel = span_to_otel(span)

    assert otel["name"] == "s"
    assert otel["trace_id"] == "t" * 32
    assert otel["status"] == "OK"
    assert otel["parent_span_id"] is None
    assert otel["attributes"]["gen_ai.request.model"] == "m"
