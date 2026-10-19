"""Optional evaluation/interop integrations."""

from .inspect_ai import (
    InspectUnavailable,
    evaluate_with_inspect,
    trace_to_sample,
    traces_to_dataset,
)

__all__ = [
    "InspectUnavailable",
    "evaluate_with_inspect",
    "trace_to_sample",
    "traces_to_dataset",
]
