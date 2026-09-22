"""API contract. See docs/architecture.md section 9."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query, Request

from pyagenthound.graph.builder import build_graph
from pyagenthound.graph.models import ExecutionGraph
from pyagenthound.rules.engine import run_rules
from pyagenthound.rules.models import Finding
from pyagenthound.sdk.models import SpanStatus, Trace, TraceSummary

router = APIRouter(prefix="/api", tags=["traces"])


@router.post("/traces", status_code=201)
def create_trace(trace: Trace, request: Request) -> Trace:
    request.app.state.store.save_trace(trace)
    return trace


@router.get("/traces")
def list_traces(
    request: Request,
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
    status: SpanStatus | None = None,
) -> list[TraceSummary]:
    return request.app.state.store.list_traces(limit=limit, offset=offset, status=status)


@router.get("/traces/{trace_id}")
def get_trace(trace_id: str, request: Request) -> Trace:
    return _get_trace_or_404(trace_id, request)


@router.get("/traces/{trace_id}/graph")
def get_trace_graph(trace_id: str, request: Request) -> ExecutionGraph:
    trace = _get_trace_or_404(trace_id, request)
    return build_graph(trace)


@router.post("/traces/{trace_id}/analyze")
def analyze_trace(trace_id: str, request: Request) -> list[Finding]:
    trace = _get_trace_or_404(trace_id, request)
    graph = build_graph(trace)
    return run_rules(trace, graph)


def _get_trace_or_404(trace_id: str, request: Request) -> Trace:
    trace = request.app.state.store.get_trace(trace_id)
    if trace is None:
        raise HTTPException(status_code=404, detail=f"trace {trace_id!r} not found")
    return trace
