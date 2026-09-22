"""Rule registry + runner. See docs/architecture.md section 5."""

from __future__ import annotations

from pyagenthound.graph.models import ExecutionGraph
from pyagenthound.rules.builtin import (
    DanglingParentSpanRule,
    DuplicateRetrievedDocumentsRule,
    EmptyRetrievalRule,
    StaleRetrievalDocumentsRule,
    ToolFailureRule,
)
from pyagenthound.rules.models import Finding, Rule
from pyagenthound.sdk.models import Trace

DEFAULT_RULES: list[Rule] = [
    EmptyRetrievalRule(),
    StaleRetrievalDocumentsRule(),
    DuplicateRetrievedDocumentsRule(),
    ToolFailureRule(),
    DanglingParentSpanRule(),
]


def run_rules(
    trace: Trace, graph: ExecutionGraph, rules: list[Rule] | None = None
) -> list[Finding]:
    findings: list[Finding] = []
    for rule in rules if rules is not None else DEFAULT_RULES:
        findings.extend(rule.evaluate(trace, graph))
    return findings
