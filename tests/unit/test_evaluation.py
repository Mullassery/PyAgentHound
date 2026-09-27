from pyagenthound.evaluation.engine import evaluate
from pyagenthound.evaluation.io import load_test_case, load_test_cases, save_test_case
from pyagenthound.evaluation.models import Assertion, AssertionType, TestCase
from pyagenthound.graph.builder import build_graph
from pyagenthound.rules.engine import run_rules
from pyagenthound.sdk.models import Span, SpanStatus, SpanType, Trace


def _trace_with_tool_and_output() -> Trace:
    trace = Trace(name="t", status=SpanStatus.OK)
    trace.spans = [
        Span(
            trace_id=trace.trace_id,
            name="llm",
            span_type=SpanType.LLM,
            output="You can cancel within 30 days.",
        ),
        Span(trace_id=trace.trace_id, name="lookup_order", span_type=SpanType.TOOL),
    ]
    return trace


def test_status_ok_assertion_passes_and_fails():
    ok_trace = Trace(name="t", status=SpanStatus.OK)
    err_trace = Trace(name="t", status=SpanStatus.ERROR)
    test_case = TestCase(
        name="t", trace_id=ok_trace.trace_id, assertions=[Assertion(type=AssertionType.STATUS_OK)]
    )

    assert evaluate(ok_trace, [], test_case).passed
    assert not evaluate(err_trace, [], test_case).passed


def test_output_contains_assertion():
    trace = _trace_with_tool_and_output()
    passing = TestCase(
        name="t",
        trace_id=trace.trace_id,
        assertions=[Assertion(type=AssertionType.OUTPUT_CONTAINS, target="30 days")],
    )
    failing = TestCase(
        name="t",
        trace_id=trace.trace_id,
        assertions=[Assertion(type=AssertionType.OUTPUT_CONTAINS, target="90 days")],
    )

    assert evaluate(trace, [], passing).passed
    assert not evaluate(trace, [], failing).passed


def test_span_exists_assertion():
    trace = _trace_with_tool_and_output()
    test_case = TestCase(
        name="t",
        trace_id=trace.trace_id,
        assertions=[Assertion(type=AssertionType.SPAN_EXISTS, target="lookup_order")],
    )
    assert evaluate(trace, [], test_case).passed

    missing = TestCase(
        name="t",
        trace_id=trace.trace_id,
        assertions=[Assertion(type=AssertionType.SPAN_EXISTS, target="charge_card")],
    )
    assert not evaluate(trace, [], missing).passed


def test_no_tool_called_assertion():
    trace = _trace_with_tool_and_output()
    test_case = TestCase(
        name="t",
        trace_id=trace.trace_id,
        assertions=[Assertion(type=AssertionType.NO_TOOL_CALLED, target="charge_card")],
    )
    assert evaluate(trace, [], test_case).passed

    test_case_fails = TestCase(
        name="t",
        trace_id=trace.trace_id,
        assertions=[Assertion(type=AssertionType.NO_TOOL_CALLED, target="lookup_order")],
    )
    assert not evaluate(trace, [], test_case_fails).passed


def test_no_finding_assertion_uses_real_rule_engine():
    trace = Trace(name="t")
    trace.spans = [
        Span(
            trace_id=trace.trace_id,
            name="retrieval",
            span_type=SpanType.RETRIEVAL,
            attributes={"documents": []},
        )
    ]
    findings = run_rules(trace, build_graph(trace))

    failing = TestCase(
        name="t",
        trace_id=trace.trace_id,
        assertions=[Assertion(type=AssertionType.NO_FINDING, target="empty_retrieval")],
    )
    passing = TestCase(
        name="t",
        trace_id=trace.trace_id,
        assertions=[Assertion(type=AssertionType.NO_FINDING, target="tool_failure")],
    )

    assert not evaluate(trace, findings, failing).passed
    assert evaluate(trace, findings, passing).passed


def test_test_case_result_fails_if_any_assertion_fails():
    trace = Trace(name="t", status=SpanStatus.ERROR)
    test_case = TestCase(
        name="t",
        trace_id=trace.trace_id,
        assertions=[
            Assertion(type=AssertionType.STATUS_OK),
            Assertion(type=AssertionType.SPAN_EXISTS, target="nonexistent"),
        ],
    )
    result = evaluate(trace, [], test_case)
    assert not result.passed
    assert len(result.assertions) == 2


def test_save_and_load_test_case_roundtrip(tmp_path):
    test_case = TestCase(
        name="my-test",
        trace_id="abc123",
        assertions=[Assertion(type=AssertionType.STATUS_OK)],
    )
    path = tmp_path / "my_test.json"

    save_test_case(test_case, path)
    loaded = load_test_case(path)

    assert loaded == test_case


def test_load_test_cases_loads_all_json_files(tmp_path):
    save_test_case(TestCase(name="a", trace_id="1"), tmp_path / "a.json")
    save_test_case(TestCase(name="b", trace_id="2"), tmp_path / "b.json")
    (tmp_path / "not_a_test.txt").write_text("ignore me")

    loaded = load_test_cases(tmp_path)

    assert {tc.name for tc in loaded} == {"a", "b"}
