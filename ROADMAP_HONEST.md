# PyAgentHound — Honest Status

**Current Version:** unreleased, Phase 2 (pre-0.1.0)
**Last Updated:** 2026-09-22

This file exists to say plainly what's built-and-verified, what's not built yet, and
what's a known, documented limitation vs. a future feature. `README.md` and
`docs/architecture.md` describe the full product vision; this file is the "have we
actually verified this" companion, so roadmap planning starts from reality.

## 🟢 Built & verified (real implementation, real test coverage)

- **Tracing model** — `Trace`, `Span`, `Event`, `SpanType`, `SpanStatus` as pydantic
  v2 models (`pyagenthound/sdk/models.py`).
- **SDK** — `AgentHound.trace()` / `TraceContext.span()` context managers,
  `@hound.trace` / `@hound.span` decorators, `contextvars`-based implicit nesting,
  `set_attribute`/`set_attributes`/`add_event`/`set_input`/`set_output`/
  `record_error`, automatic `status=ERROR` + error capture on uncaught exception.
- **Storage** — `TraceStore` protocol + `SQLiteTraceStore` (save/get/list, JSON
  columns for attributes/events/tags/metadata).
- **Export** — `LocalSQLiteExporter` (default, no server required) and
  `HTTPExporter` (POSTs to `{endpoint}/api/traces` when configured); export failures
  are caught and logged, never raised into the host app.
- **API** — FastAPI app with `POST /api/traces`, `GET /api/traces`,
  `GET /api/traces/{id}`, `GET /api/traces/{id}/graph`; OpenAPI docs at `/docs`.
- **CLI** — `pyagenthound init`, `pyagenthound serve`, `pyagenthound inspect <id>`.
- **Execution graph** — `pyagenthound/graph/`: `Node`/`Edge`/`ExecutionGraph` domain
  model with query methods (`nodes_by_type`, `edges_by_relationship`,
  `nodes_in_window`, `outgoing`/`incoming`/`neighbors`, `ancestors`); `build_graph()`
  walks a trace into a `TRACE` root + per-span nodes linked by `PARENT` edges. One
  attribute extractor is implemented: `RETRIEVAL` spans' `documents` attribute
  produces `DOCUMENT` nodes + `RETRIEVES` edges (basic data lineage). Extractors for
  other span types (tool args, MCP resources, etc.) are not built — see the 🟡
  section below.

Re-verify this list's "🟢" claims by actually running `pytest -q` — a memory of "it
passed once" is not the same as it passing now.

## 🟡 Documented design, not implemented yet

These have a designed contract in `docs/architecture.md` so later work builds against
a stable shape, but zero implementation exists:

- Graph extractors beyond `RETRIEVAL` (tool arguments, MCP resources/prompts,
  embedding inputs, reranking scores, etc.) — the registry pattern in
  `pyagenthound/graph/builder.py` supports adding these incrementally.
- Deterministic rule engine / `Finding`s.
- Root-cause engine, confidence model, historical baseline comparison.
- LLM-powered (optional) analysis layer.
- Retrieval-specific, tool/MCP-specific, model-specific, prompt-specific analyzers.
- Replay (including the READ_ONLY/WRITE/DESTRUCTIVE safety classification).
- Regression test suite / `pyagenthound test` CLI command.
- Full data/context lineage beyond the single `RETRIEVAL` → `DOCUMENT` extractor.

## 🔴 Explicitly out of scope for now

- Web UI (no `ui/` exists).
- OpenTelemetry SDK ingestion adapter — the domain model is OTel-*compatible* in
  shape, but nothing consumes real OTel traces yet.
- MCP integration, LangChain/LangGraph framework adapters.
- Redaction / PII scrubbing / configurable capture modes (metadata-only, hashed).
  Treat everything captured today as unredacted and sensitive.
- Any Rust component. Phase 1 is pure Python — see `README.md` design principles.
  Rust is added later only where profiling identifies a real need (PyO3), not by
  default.
- PyPI publication.
- Authentication on the API server (`pyagenthound serve` is meant for localhost).

## Known Phase-1 limitations (not bugs, just not built)

- Export is synchronous, unbatched, unsampled — fine for local dev, not designed for
  high-throughput production use yet.
- No payload-size limits on spans; a very large `attributes`/`input`/`output` value
  will be stored as-is.
- `list_traces` supports only `limit`/`offset`/`status` filtering — no full-text or
  attribute search.
