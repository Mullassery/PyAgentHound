# PyAgentHound — Honest Status

**Current Version:** unreleased, Phase 6 (pre-0.1.0)
**Last Updated:** 2026-09-27

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
- **API** — FastAPI app with `POST /api/traces`, `GET /api/traces` (`limit`,
  `offset`, `status`, `name`), `GET /api/traces/{id}`, `GET /api/traces/{id}/graph`,
  `POST /api/traces/{id}/analyze`, `GET /api/traces/{id}/root-cause`,
  `POST /api/traces/{id}/replay` (`409` if an unconfirmed unsafe override is
  requested); OpenAPI docs at `/docs`.
- **CLI** — `pyagenthound init`, `pyagenthound serve`, `pyagenthound inspect <id>`,
  `pyagenthound analyze <id>` (prints findings, baseline comparison when available,
  and ranked root-cause hypotheses), `pyagenthound replay <id> --set NAME.KEY=VALUE
  [--allow-unsafe]`.
- **Execution graph** — `pyagenthound/graph/`: `Node`/`Edge`/`ExecutionGraph` domain
  model with query methods (`nodes_by_type`, `edges_by_relationship`,
  `nodes_in_window`, `outgoing`/`incoming`/`neighbors`, `ancestors`); `build_graph()`
  walks a trace into a `TRACE` root + per-span nodes linked by `PARENT` edges. One
  attribute extractor is implemented: `RETRIEVAL` spans' `documents` attribute
  produces `DOCUMENT` nodes + `RETRIEVES` edges (basic data lineage). Extractors for
  other span types (tool args, MCP resources, etc.) are not built — see the 🟡
  section below.
- **Rule engine** — `pyagenthound/rules/`: `Finding`/`Evidence`/`FailureCategory`/
  `Severity` domain model, `Rule` protocol, `run_rules()`. Five built-in rules, each
  with passing positive/negative unit tests: `empty_retrieval`,
  `stale_retrieval_documents` (the deterministic signal behind the stale-context demo
  scenario), `duplicate_retrieved_documents`, `tool_failure`, `dangling_parent_span`.
  `Finding.confidence` is each rule's own certainty about its specific anomaly — it
  is a component of, but not equal to, root-cause confidence (see next item).
- **Root-cause engine** — `pyagenthound/rootcause/`: `ConfidenceComponents`/
  `RootCauseHypothesis` domain model, `rank_root_causes()`. Turns each `Finding`
  into a hypothesis, ranks by confidence, labels the top one `likely_cause` and the
  rest `contributing_factor`. All four documented confidence components are
  implemented (`evidence_strength`, `causal_proximity`, `temporal_correlation`,
  `historical_frequency` — see next item for the last two), combined via a weighted
  average that renormalizes over whichever are present for a given finding. No
  fabricated "observed consequence" (e.g. claiming an answer was "incorrect") is
  generated; that would require ground truth this system doesn't have.
- **Historical baselines** — `pyagenthound/baseline/`: `ExecutionSignature` +
  `extract_signature()` (model, prompt version, retriever, tools, latency, tokens,
  execution path), `find_baseline()` (most recent prior `status=OK` execution with
  the same `trace.name`), `compare_to_baseline()` (emits a `Finding` per changed
  field — `baseline_model_changed`, `baseline_prompt_changed`,
  `baseline_retriever_changed`, `baseline_tools_changed`,
  `baseline_execution_path_changed`, `baseline_latency_regression`,
  `baseline_token_growth` — every description states an observed change, never a
  causal claim), `historical_rule_frequencies()` (fraction of recent same-named
  traces where a given `rule_id` also fired). Wired into `POST .../analyze`,
  `GET .../root-cause`, and `pyagenthound analyze`.
- **Replay** — `pyagenthound/replay/`: `classify_span_safety()` (READ_ONLY/WRITE/
  DESTRUCTIVE/UNKNOWN, conservative defaults — only RETRIEVAL/EMBEDDING/RERANKING/
  LLM/PROMPT default to READ_ONLY, everything else UNKNOWN unless explicitly
  annotated), `build_plan()`, `apply_overrides()` (clones a trace with fresh ids +
  per-span attribute overrides — a counterfactual edit, not a re-invocation of the
  agent), `run_replay()` (safety-gated: raises `UnsafeReplayError` for an
  unconfirmed non-READ_ONLY override; otherwise re-runs the rule engine on both
  traces and returns the finding diff). Verified end to end against the real
  stale-document scenario: overriding `retrieval.documents` to just the current
  policy resolved `stale_retrieval_documents` (1 finding → 0), via both
  `pyagenthound replay` and `POST .../replay`.

Re-verify this list's "🟢" claims by actually running `pytest -q` — a memory of "it
passed once" is not the same as it passing now.

## 🟡 Documented design, not implemented yet

These have a designed contract in `docs/architecture.md` so later work builds against
a stable shape, but zero implementation exists:

- Graph extractors beyond `RETRIEVAL` (tool arguments, MCP resources/prompts,
  embedding inputs, reranking scores, etc.) — the registry pattern in
  `pyagenthound/graph/builder.py` supports adding these incrementally.
- The remaining rules from product spec section 6.5 beyond the 5 built-in ones —
  low-relevance retrieval, excessive/token-explosion context, malformed tool
  arguments, schema mismatches, tool/agent loops, timeout propagation, failed
  guardrails, output schema violations, etc. (model/prompt change detection is
  now covered by baseline comparison, not a rule-engine rule).
- LLM-powered (optional) analysis layer.
- Replaying by actually re-invoking a live model/tool/retriever — today's replay
  only edits recorded attributes and re-analyzes; it never calls anything.
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

## Known limitations (not bugs, just not built)

- Export is synchronous, unbatched, unsampled — fine for local dev, not designed for
  high-throughput production use yet.
- No payload-size limits on spans; a very large `attributes`/`input`/`output` value
  will be stored as-is.
- `list_traces` supports `limit`/`offset`/`status`/`name` filtering — no full-text or
  attribute search.
- "Same logical workflow" for baseline purposes means `trace.name` matches exactly —
  no fuzzy grouping, no per-tenant scoping. Two genuinely different workflows that
  happen to share a name will be (incorrectly) compared against each other.
- `historical_rule_frequencies` re-runs the full rule engine against every candidate
  historical trace on every call — fine at the `lookback` default of 20 and local
  SQLite scale, not optimized for a large trace history.
- `causal_proximity`'s "final span = latest `end_time`" heuristic is a proxy, not a
  real understanding of data flow — sibling spans (e.g. retrieval and the LLM call
  that consumes its output, if not nested as parent→child) get the same low
  off-path score as truly unrelated branches. See `docs/architecture.md` section 6
  and the real example in `README.md`.
