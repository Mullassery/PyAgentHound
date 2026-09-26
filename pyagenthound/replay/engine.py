"""Replay execution. See docs/architecture.md section 13."""

from __future__ import annotations

import uuid
from typing import Any

from pyagenthound.graph.builder import build_graph
from pyagenthound.replay.models import ReplayPlan, ReplayResult, ReplayStep
from pyagenthound.replay.safety import classify_span_safety
from pyagenthound.rules.engine import run_rules
from pyagenthound.sdk.models import Trace
from pyagenthound.storage.base import TraceStore


class UnsafeReplayError(RuntimeError):
    """Raised when a replay would override a non-READ_ONLY span without confirmation."""


def build_plan(trace: Trace, overrides: dict[str, dict[str, Any]]) -> ReplayPlan:
    steps = [
        ReplayStep(
            span_id=span.span_id,
            name=span.name,
            span_type=span.span_type,
            safety=classify_span_safety(span),
            overrides=overrides.get(span.span_id, {}),
        )
        for span in trace.spans
    ]
    return ReplayPlan(trace_id=trace.trace_id, steps=steps)


def apply_overrides(trace: Trace, overrides: dict[str, dict[str, Any]]) -> Trace:
    """Clone `trace` with fresh trace/span ids and the given per-original-span-id
    attribute overrides applied. Does not execute anything — this is a counterfactual
    edit of already-captured data, not a re-invocation of the agent.
    """
    replayed = trace.model_copy(deep=True)
    replayed.trace_id = uuid.uuid4().hex
    replayed.tags = [*replayed.tags, "replay"]
    replayed.metadata = {**replayed.metadata, "replayed_from": trace.trace_id}

    id_map = {span.span_id: uuid.uuid4().hex[:16] for span in trace.spans}
    for span in replayed.spans:
        original_id = span.span_id
        span.span_id = id_map[original_id]
        span.trace_id = replayed.trace_id
        if span.parent_span_id is not None and span.parent_span_id in id_map:
            span.parent_span_id = id_map[span.parent_span_id]
        span.attributes.update(overrides.get(original_id, {}))

    return replayed


def run_replay(
    store: TraceStore,
    trace: Trace,
    overrides: dict[str, dict[str, Any]],
    allow_unsafe: bool = False,
) -> ReplayResult:
    plan = build_plan(trace, overrides)
    if plan.requires_confirmation and not allow_unsafe:
        unsafe_names = [step.name for step in plan.unsafe_steps]
        raise UnsafeReplayError(
            f"Replay would override non-READ_ONLY span(s) {unsafe_names} — "
            "pass allow_unsafe=True to confirm."
        )

    original_findings = run_rules(trace, build_graph(trace))

    replayed_trace = apply_overrides(trace, overrides)
    replayed_findings = run_rules(replayed_trace, build_graph(replayed_trace))
    store.save_trace(replayed_trace)

    original_rule_ids = {f.rule_id for f in original_findings}
    replayed_rule_ids = {f.rule_id for f in replayed_findings}

    return ReplayResult(
        original_trace_id=trace.trace_id,
        replayed_trace_id=replayed_trace.trace_id,
        plan=plan,
        original_findings=original_findings,
        replayed_findings=replayed_findings,
        resolved_rule_ids=sorted(original_rule_ids - replayed_rule_ids),
        new_rule_ids=sorted(replayed_rule_ids - original_rule_ids),
    )
