"""Assertion evaluation. See docs/architecture.md section 14."""

from __future__ import annotations

from pyagenthound.evaluation.models import (
    Assertion,
    AssertionResult,
    AssertionType,
    TestCase,
    TestCaseResult,
)
from pyagenthound.rules.models import Finding
from pyagenthound.sdk.models import SpanStatus, SpanType, Trace


def evaluate(trace: Trace, findings: list[Finding], test_case: TestCase) -> TestCaseResult:
    results = [_check(assertion, trace, findings) for assertion in test_case.assertions]
    return TestCaseResult(
        name=test_case.name,
        trace_id=test_case.trace_id,
        passed=all(r.passed for r in results),
        assertions=results,
    )


def _check(assertion: Assertion, trace: Trace, findings: list[Finding]) -> AssertionResult:
    if assertion.type == AssertionType.STATUS_OK:
        passed = trace.status == SpanStatus.OK
        return AssertionResult(
            assertion=assertion, passed=passed, message=f"trace.status == {trace.status.value}"
        )

    if assertion.type == AssertionType.OUTPUT_CONTAINS:
        haystack = " ".join(str(span.output) for span in trace.spans if span.output is not None)
        passed = assertion.target is not None and assertion.target in haystack
        return AssertionResult(
            assertion=assertion,
            passed=passed,
            message=f"looked for {assertion.target!r} in span outputs",
        )

    if assertion.type == AssertionType.NO_FINDING:
        matching = [
            f
            for f in findings
            if f.rule_id == assertion.target or f.category.value == assertion.target
        ]
        passed = len(matching) == 0
        return AssertionResult(
            assertion=assertion,
            passed=passed,
            message=f"{len(matching)} finding(s) matched {assertion.target!r}",
        )

    if assertion.type == AssertionType.SPAN_EXISTS:
        passed = any(span.name == assertion.target for span in trace.spans)
        return AssertionResult(
            assertion=assertion,
            passed=passed,
            message=f"span {assertion.target!r} {'found' if passed else 'not found'}",
        )

    if assertion.type == AssertionType.NO_TOOL_CALLED:
        called = sorted(
            {span.name for span in trace.spans if span.span_type in (SpanType.TOOL, SpanType.MCP)}
        )
        passed = assertion.target not in called
        return AssertionResult(
            assertion=assertion, passed=passed, message=f"tools called: {called}"
        )

    raise ValueError(f"unknown assertion type: {assertion.type}")
