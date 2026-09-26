"""Storage interface. See docs/architecture.md section 7.

`SQLiteTraceStore` is the only Phase-1 implementation. This Protocol exists so a
future Postgres-backed store can be added without any caller changing.
"""

from __future__ import annotations

from typing import Protocol

from pyagenthound.sdk.models import SpanStatus, Trace, TraceSummary


class TraceStore(Protocol):
    def init_schema(self) -> None: ...

    def save_trace(self, trace: Trace) -> None: ...

    def get_trace(self, trace_id: str) -> Trace | None: ...

    def list_traces(
        self,
        limit: int = 50,
        offset: int = 0,
        status: SpanStatus | None = None,
        name: str | None = None,
    ) -> list[TraceSummary]: ...
