"""SDK client. See docs/architecture.md section 7.

Current trace/span is tracked via `contextvars.ContextVar` — the same mechanism
OpenTelemetry uses for context propagation — so `@hound.span` decorators and nested
`with` blocks share context implicitly, without passing a trace/span object around.
"""

from __future__ import annotations

import functools
import traceback
from collections.abc import Callable
from contextvars import ContextVar
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, TypeVar

from pyagenthound.config import DEFAULT_DB_PATH
from pyagenthound.sdk.exporter import Exporter, HTTPExporter, LocalSQLiteExporter
from pyagenthound.sdk.models import Event, Span, SpanError, SpanStatus, SpanType, Trace

F = TypeVar("F", bound=Callable[..., Any])


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


_current_trace: ContextVar[TraceContext | None] = ContextVar(
    "pyagenthound_current_trace", default=None
)
_current_span: ContextVar[SpanContext | None] = ContextVar(
    "pyagenthound_current_span", default=None
)


class SpanContext:
    """An in-flight span, tied to a specific `TraceContext`. Returned by `trace.span(...)`."""

    def __init__(self, trace_ctx: TraceContext, span: Span):
        self._trace_ctx = trace_ctx
        self.span = span
        self._token: Any = None

    def set_attribute(self, key: str, value: Any) -> None:
        self.span.attributes[key] = value

    def set_attributes(self, attributes: dict[str, Any]) -> None:
        self.span.attributes.update(attributes)

    def add_event(self, name: str, attributes: dict[str, Any] | None = None) -> None:
        self.span.events.append(Event(name=name, attributes=attributes or {}))

    def set_input(self, value: Any) -> None:
        self.span.input = value

    def set_output(self, value: Any) -> None:
        self.span.output = value

    def record_error(self, exc: BaseException) -> None:
        self.span.status = SpanStatus.ERROR
        self.span.error = SpanError(
            type=type(exc).__name__,
            message=str(exc),
            stacktrace="".join(traceback.format_exception(type(exc), exc, exc.__traceback__)),
        )

    def __enter__(self) -> SpanContext:
        self._token = _current_span.set(self)
        return self

    def __exit__(self, exc_type: Any, exc: BaseException | None, tb: Any) -> None:
        self.span.end_time = _utcnow()
        if exc is not None:
            self.record_error(exc)
        elif self.span.status == SpanStatus.UNSET:
            self.span.status = SpanStatus.OK
        _current_span.reset(self._token)
        assert self._trace_ctx.trace is not None
        self._trace_ctx.trace.spans.append(self.span)


class _SpanDecorator:
    """Returned by `hound.span(name, ...)`. Requires an active trace at call time."""

    def __init__(self, name: str, span_type: SpanType = SpanType.CUSTOM):
        self._name = name
        self._span_type = span_type

    def __call__(self, func: F) -> F:
        @functools.wraps(func)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            trace_ctx = _current_trace.get()
            if trace_ctx is None:
                raise RuntimeError(
                    f"@hound.span({self._name!r}) used outside an active trace — "
                    "wrap the call in `with hound.trace(...):` or `@hound.trace(...)`"
                )
            with trace_ctx.span(self._name, span_type=self._span_type):
                return func(*args, **kwargs)

        return wrapper  # type: ignore[return-value]


class TraceContext:
    """Returned by `hound.trace(name)`. Usable as a context manager or as a decorator."""

    def __init__(
        self,
        hound: AgentHound,
        name: str,
        tags: list[str] | None = None,
        metadata: dict[str, Any] | None = None,
    ):
        self._hound = hound
        self._name = name
        self._tags = list(tags or [])
        self._metadata = dict(metadata or {})
        self.trace: Trace | None = None
        self._token: Any = None

    def span(self, name: str, span_type: SpanType = SpanType.CUSTOM) -> SpanContext:
        if self.trace is None:
            raise RuntimeError(
                "trace.span() called outside an active `with hound.trace(...)` block"
            )
        parent = _current_span.get()
        parent_span_id = parent.span.span_id if parent is not None else None
        span = Span(
            trace_id=self.trace.trace_id,
            parent_span_id=parent_span_id,
            name=name,
            span_type=span_type,
        )
        return SpanContext(self, span)

    def __enter__(self) -> TraceContext:
        self.trace = Trace(name=self._name, tags=list(self._tags), metadata=dict(self._metadata))
        self._token = _current_trace.set(self)
        return self

    def __exit__(self, exc_type: Any, exc: BaseException | None, tb: Any) -> None:
        assert self.trace is not None
        self.trace.end_time = _utcnow()
        if exc is not None:
            self.trace.status = SpanStatus.ERROR
        elif self.trace.status == SpanStatus.UNSET:
            self.trace.status = SpanStatus.OK
        _current_trace.reset(self._token)
        self._hound._export(self.trace)

    def __call__(self, func: F) -> F:
        @functools.wraps(func)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            tags = list(self._tags)
            metadata = dict(self._metadata)
            with self._hound.trace(self._name, tags=tags, metadata=metadata):
                return func(*args, **kwargs)

        return wrapper  # type: ignore[return-value]


class AgentHound:
    """Entry point for the SDK.

    `AgentHound()` (no `endpoint`) is local-first: traces are written straight to a
    SQLite file at `db_path` (default `~/.pyagenthound/pyagenthound.db`), no server
    required. Passing `endpoint="http://localhost:8787"` sends traces to a running
    `pyagenthound serve` instance instead.
    """

    def __init__(self, endpoint: str | None = None, db_path: str | Path | None = None):
        self._exporter: Exporter
        if endpoint is not None:
            self._exporter = HTTPExporter(endpoint)
        else:
            self._exporter = LocalSQLiteExporter(db_path or DEFAULT_DB_PATH)

    def trace(
        self,
        name: str,
        tags: list[str] | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> TraceContext:
        return TraceContext(self, name, tags=tags, metadata=metadata)

    def span(self, name: str, span_type: SpanType = SpanType.CUSTOM) -> _SpanDecorator:
        return _SpanDecorator(name, span_type=span_type)

    def _export(self, trace: Trace) -> None:
        self._exporter.export(trace)
