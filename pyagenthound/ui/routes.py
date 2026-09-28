"""Server-rendered web UI. See docs/architecture.md section 15.

Deliberately server-rendered (FastAPI + Jinja2), not a JS SPA — no npm/build step,
consistent with "Python is the primary developer API" (README design principles).
The one place vanilla JS is used is the execution graph (`static/graph.js`), which
fetches the same `GET /api/traces/{id}/graph` JSON the API already serves — the UI
is a thin client of its own API, not a second implementation of graph construction.
"""

from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

from pyagenthound.baseline.engine import compare_to_baseline, find_baseline
from pyagenthound.baseline.signature import extract_signature
from pyagenthound.graph.builder import build_graph
from pyagenthound.replay.engine import (
    UnsafeReplayError,
    overrides_by_span_id,
    parse_override,
    run_replay,
)
from pyagenthound.rootcause.engine import rank_root_causes
from pyagenthound.rules.engine import run_rules
from pyagenthound.sdk.models import SpanStatus, Trace

router = APIRouter()

_templates = Jinja2Templates(directory=str(Path(__file__).parent / "templates"))


@router.get("/", response_class=HTMLResponse)
def requests_list(
    request: Request, status: str | None = None, name: str | None = None
) -> HTMLResponse:
    store = request.app.state.store
    status_enum = SpanStatus(status) if status else None
    traces = store.list_traces(limit=100, status=status_enum, name=name or None)
    return _templates.TemplateResponse(
        request,
        "requests_list.html",
        {"traces": traces, "status_filter": status, "name_filter": name},
    )


@router.get("/requests/{trace_id}", response_class=HTMLResponse)
def request_detail(
    request: Request, trace_id: str, replay_error: str | None = None
) -> HTMLResponse:
    trace = _get_trace_or_404(request, trace_id)
    graph = build_graph(trace)
    findings = run_rules(trace, graph)

    baseline = find_baseline(request.app.state.store, trace)
    if baseline is not None:
        findings = [*findings, *compare_to_baseline(trace, baseline)]

    hypotheses = rank_root_causes(trace, graph, store=request.app.state.store)
    signature = extract_signature(trace)

    return _templates.TemplateResponse(
        request,
        "request_detail.html",
        {
            "trace": trace,
            "signature": signature,
            "findings": findings,
            "hypotheses": hypotheses,
            "baseline": baseline,
            "replayed_from": trace.metadata.get("replayed_from"),
            "replay_error": replay_error,
        },
    )


@router.post("/requests/{trace_id}/replay")
def replay_from_ui(
    request: Request,
    trace_id: str,
    override: str = Form(...),
    allow_unsafe: str | None = Form(None),
) -> RedirectResponse:
    trace = _get_trace_or_404(request, trace_id)
    name, key, value = parse_override(override)
    if not name or not key:
        return RedirectResponse(
            f"/requests/{trace_id}?replay_error=Override must look like NAME.KEY=VALUE",
            status_code=303,
        )

    try:
        result = run_replay(
            request.app.state.store,
            trace,
            overrides_by_span_id(trace, {name: {key: value}}),
            allow_unsafe=bool(allow_unsafe),
        )
    except UnsafeReplayError as exc:
        return RedirectResponse(f"/requests/{trace_id}?replay_error={exc}", status_code=303)

    return RedirectResponse(f"/requests/{result.replayed_trace_id}", status_code=303)


def _get_trace_or_404(request: Request, trace_id: str) -> Trace:
    trace = request.app.state.store.get_trace(trace_id)
    if trace is None:
        raise HTTPException(status_code=404, detail=f"trace {trace_id!r} not found")
    return trace
