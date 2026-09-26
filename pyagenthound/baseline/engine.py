"""Historical baseline comparison. See docs/architecture.md section 6.

Two independent signals, both requiring the trace store (unlike the stateless
`Rule.evaluate(trace, graph)` rules, which never depend on other traces):

- `compare_to_baseline` diffs the current trace's `ExecutionSignature` against the
  most recent prior *successful* execution of the same named workflow. Every
  resulting `Finding` states an observed change, never a causal claim (product spec
  section 6.8: "Do not automatically claim causality").
- `historical_rule_frequencies` runs the stateless rule engine against recent prior
  executions (any status) of the same workflow and reports, per `rule_id`, what
  fraction of them also produced that finding — the `historical_frequency`
  confidence component. A high frequency means the anomaly is a recurring, familiar
  pattern; it is not by itself evidence that the pattern is the correct root cause.
"""

from __future__ import annotations

from pyagenthound.baseline.signature import extract_signature
from pyagenthound.graph.builder import build_graph
from pyagenthound.rules.engine import run_rules
from pyagenthound.rules.models import Evidence, FailureCategory, Finding, Severity
from pyagenthound.sdk.models import SpanStatus, Trace
from pyagenthound.storage.base import TraceStore

_REGRESSION_FACTOR = 1.5


def find_baseline(store: TraceStore, trace: Trace, lookback: int = 20) -> Trace | None:
    """Most recent prior successful execution of the same named workflow, or None."""
    candidates = store.list_traces(limit=lookback, status=SpanStatus.OK, name=trace.name)
    for summary in candidates:
        if summary.trace_id != trace.trace_id:
            return store.get_trace(summary.trace_id)
    return None


def compare_to_baseline(trace: Trace, baseline: Trace) -> list[Finding]:
    current = extract_signature(trace)
    previous = extract_signature(baseline)
    findings: list[Finding] = []

    if _differs(current.model, previous.model):
        findings.append(
            _change_finding(
                "baseline_model_changed",
                FailureCategory.MODEL_FAILURE,
                "model",
                previous.model,
                current.model,
                baseline.trace_id,
                trace.trace_id,
            )
        )
    if _differs(current.prompt_version, previous.prompt_version):
        findings.append(
            _change_finding(
                "baseline_prompt_changed",
                FailureCategory.PROMPT_FAILURE,
                "prompt version",
                previous.prompt_version,
                current.prompt_version,
                baseline.trace_id,
                trace.trace_id,
            )
        )
    if _differs(current.retriever, previous.retriever):
        findings.append(
            _change_finding(
                "baseline_retriever_changed",
                FailureCategory.RETRIEVAL_FAILURE,
                "retriever",
                previous.retriever,
                current.retriever,
                baseline.trace_id,
                trace.trace_id,
            )
        )
    if current.tools != previous.tools:
        findings.append(
            _change_finding(
                "baseline_tools_changed",
                FailureCategory.CONFIGURATION_FAILURE,
                "tools invoked",
                ", ".join(previous.tools) or "none",
                ", ".join(current.tools) or "none",
                baseline.trace_id,
                trace.trace_id,
            )
        )
    if current.execution_path != previous.execution_path:
        findings.append(
            _change_finding(
                "baseline_execution_path_changed",
                FailureCategory.CONFIGURATION_FAILURE,
                "execution path",
                " -> ".join(previous.execution_path) or "empty",
                " -> ".join(current.execution_path) or "empty",
                baseline.trace_id,
                trace.trace_id,
            )
        )
    if _regressed(current.latency_ms, previous.latency_ms):
        findings.append(
            _regression_finding(
                "baseline_latency_regression",
                FailureCategory.PERFORMANCE_FAILURE,
                "latency",
                previous.latency_ms,
                current.latency_ms,
                "ms",
                baseline.trace_id,
                trace.trace_id,
            )
        )
    if _regressed(current.total_tokens, previous.total_tokens):
        findings.append(
            _regression_finding(
                "baseline_token_growth",
                FailureCategory.CONTEXT_FAILURE,
                "total tokens",
                previous.total_tokens,
                current.total_tokens,
                " tokens",
                baseline.trace_id,
                trace.trace_id,
            )
        )

    return findings


def historical_rule_frequencies(
    store: TraceStore, trace: Trace, lookback: int = 20
) -> dict[str, float]:
    """`rule_id -> fraction of recent same-workflow traces where it also fired`.

    Only covers stateless rule-engine findings, never `baseline_*` findings —
    computing baseline comparisons recursively for every historical trace would be
    O(lookback^2) for a signal of debatable value (each baseline finding already
    carries its own `temporal_correlation`).
    """
    candidates = [
        summary
        for summary in store.list_traces(limit=lookback, name=trace.name)
        if summary.trace_id != trace.trace_id
    ]
    if not candidates:
        return {}

    counts: dict[str, int] = {}
    total = 0
    for summary in candidates:
        historical_trace = store.get_trace(summary.trace_id)
        if historical_trace is None:
            continue
        total += 1
        historical_graph = build_graph(historical_trace)
        rule_ids = {finding.rule_id for finding in run_rules(historical_trace, historical_graph)}
        for rule_id in rule_ids:
            counts[rule_id] = counts.get(rule_id, 0) + 1

    if total == 0:
        return {}
    return {rule_id: count / total for rule_id, count in counts.items()}


def _differs(current: str | None, previous: str | None) -> bool:
    return current is not None and previous is not None and current != previous


def _regressed(current: float | None, previous: float | None) -> bool:
    return (
        current is not None
        and previous is not None
        and previous > 0
        and current > previous * _REGRESSION_FACTOR
    )


def _change_finding(
    rule_id: str,
    category: FailureCategory,
    field: str,
    previous: object,
    current: object,
    baseline_trace_id: str,
    trace_id: str,
) -> Finding:
    return Finding(
        rule_id=rule_id,
        category=category,
        severity=Severity.MEDIUM,
        title=f"{field.capitalize()} changed since the last successful execution",
        description=(
            f"{field} was {previous!r} in the most recent successful execution "
            f"({baseline_trace_id}) and is {current!r} now. This is an observed "
            "change, not a claim that it caused the current outcome."
        ),
        evidence=[
            Evidence(
                description=f"baseline {field}: {previous!r}; current {field}: {current!r}",
                data={
                    "baseline_trace_id": baseline_trace_id,
                    "previous": previous,
                    "current": current,
                },
            )
        ],
        affected_nodes=[trace_id],
        confidence=1.0,
        recommendation=f"Investigate whether the {field} change contributed to the current result.",
    )


def _regression_finding(
    rule_id: str,
    category: FailureCategory,
    field: str,
    previous: float | None,
    current: float | None,
    unit: str,
    baseline_trace_id: str,
    trace_id: str,
) -> Finding:
    assert previous is not None and current is not None
    ratio_text = f" ({current / previous:.1f}x)" if previous else ""
    return Finding(
        rule_id=rule_id,
        category=category,
        severity=Severity.MEDIUM,
        title=f"{field.capitalize()} increased since the last successful execution",
        description=(
            f"{field} was {previous:.0f}{unit} in the most recent successful execution "
            f"({baseline_trace_id}) and is {current:.0f}{unit} now{ratio_text}. This is "
            "an observed change, not a claim that it caused the current outcome."
        ),
        evidence=[
            Evidence(
                description=(
                    f"baseline {field}: {previous:.0f}{unit}; current {field}: {current:.0f}{unit}"
                ),
                data={
                    "baseline_trace_id": baseline_trace_id,
                    "previous": previous,
                    "current": current,
                },
            )
        ],
        affected_nodes=[trace_id],
        confidence=1.0,
        recommendation=(
            f"Investigate whether the {field} increase contributed to the current result."
        ),
    )
