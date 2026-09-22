"""API contract. See docs/architecture.md section 9."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query, Request

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
    trace = request.app.state.store.get_trace(trace_id)
    if trace is None:
        raise HTTPException(status_code=404, detail=f"trace {trace_id!r} not found")
    return trace
