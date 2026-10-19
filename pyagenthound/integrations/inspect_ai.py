"""Inspect AI interop.

Inspect AI (MIT) is an evaluation framework for agent/LLM tasks. This adapter
turns recorded PyAgentHound traces into Inspect ``Sample`` objects and can run
an Inspect task against them. Trace evidence remains the source of truth; the
adapter does not fabricate targets.
"""

from __future__ import annotations

from collections.abc import Iterable
from typing import Any

from pyagenthound.sdk.models import Trace


class InspectUnavailable(RuntimeError):
    """Raised when inspect-ai is not installed."""


def _require_inspect():
    try:
        from inspect_ai import Task, eval
        from inspect_ai.dataset import Sample
    except ImportError as exc:
        raise InspectUnavailable(
            'Inspect AI is not installed. Install with `pip install "pyagenthound[inspect]"`.'
        ) from exc
    return Task, eval, Sample


def _input_text(trace: Trace) -> str:
    inputs = [str(span.input) for span in trace.spans if span.input is not None]
    return "\n".join(inputs) if inputs else trace.name


def _target_text(trace: Trace) -> str:
    outputs = [str(span.output) for span in trace.spans if span.output is not None]
    if outputs:
        return outputs[-1]
    return ""


def trace_to_sample(trace: Trace) -> dict[str, Any]:
    """Return an Inspect-shaped sample dict (input/target/metadata/id)."""
    return {
        "id": trace.trace_id,
        "input": _input_text(trace),
        "target": _target_text(trace),
        "metadata": {
            "trace_id": trace.trace_id,
            "name": trace.name,
            "status": trace.status.value,
            "tags": list(trace.tags),
            "span_count": len(trace.spans),
        },
    }


def traces_to_dataset(traces: Iterable[Trace]) -> list[dict[str, Any]]:
    return [trace_to_sample(trace) for trace in traces]


def evaluate_with_inspect(
    traces: Iterable[Trace],
    task: Any,
    *,
    model: str,
    limit: int | None = None,
) -> Any:
    """Run an Inspect AI task over traces converted to Samples.

    ``task`` may be an Inspect ``Task`` returning a solver/scorer pipeline that
    uses the sample input/target. The function returns Inspect's eval result.
    """
    Task, eval_fn, Sample = _require_inspect()
    samples = [
        Sample(
            id=sample["id"],
            input=sample["input"],
            target=sample["target"],
            metadata=sample["metadata"],
        )
        for sample in traces_to_dataset(traces)
    ]
    if isinstance(task, Task):
        task.dataset = samples
    return eval_fn(task, model=model, limit=limit)


__all__ = [
    "InspectUnavailable",
    "evaluate_with_inspect",
    "trace_to_sample",
    "traces_to_dataset",
]
