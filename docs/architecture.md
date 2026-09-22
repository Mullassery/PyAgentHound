# PyAgentHound — Architecture

This document is the architecture deliverable for the project: it identifies MVP
boundaries, core domain models, API contracts, the execution-graph model, the rule
engine interface, storage interfaces, the SDK API, security/privacy boundaries, and
testing strategy. Sections marked **(Phase 1)** are implemented today. Sections marked
**(future)** describe the intended contract so later phases build against a stable
shape, not because the code exists yet — see `ROADMAP_HONEST.md` for exactly what's
real right now.

## 1. Product framing

Traditional observability answers "what happened?" PyAgentHound's job is to answer
"why did my AI application produce this result?" — it does that by collecting
execution **evidence**, assembling it into a causal **execution graph**, and running
**analysis** over that graph to produce evidence-backed **findings** and ranked
**root-cause hypotheses**. The core pipeline, end to end:

```
Trace → Graph → Evidence → Findings → Causal hypotheses → Replay → Evaluation
```

Four kinds of statements the system can make, never conflated:

- **Observed facts** — directly read off spans/attributes (e.g. "3 documents were
  retrieved").
- **Detected anomalies** — deterministic rule matches (e.g. "document date predates
  the active policy version").
- **Inferred causes** — root-cause hypotheses with a confidence score, always
  evidence-referenced, never presented as fact.
- **Recommendations** — remediation hints attached to a finding/category.

## 2. MVP boundary (Phase 1)

Phase 1 delivers the substrate everything else builds on: capture a trace, store it,
retrieve it, look at it. No graph construction, no rules, no root-cause engine, no UI,
no replay, no eval yet. Concretely, Phase 1 = SDK + tracing model + SQLite storage +
a 3-endpoint API + a 3-command CLI. See `ROADMAP_HONEST.md` for the authoritative
built-vs-not list.

## 3. Domain models (Phase 1)

Defined in `pyagenthound/sdk/models.py` as pydantic v2 models — reused directly as
API request/response schemas so there's exactly one definition of "what a trace is."

- **`SpanType`** — semantic category of a span: `AGENT, LLM, RETRIEVAL, EMBEDDING,
  RERANKING, TOOL, MCP, API, DATABASE, VECTOR_DB, PROMPT, MEMORY, GUARDRAIL,
  EVALUATION, CUSTOM`. Deliberately an open-ended enum with `CUSTOM` as a fallback —
  span *attributes* are unstructured (`dict[str, Any]`), never a fixed schema, so a
  new AI-specific field never requires a migration.
- **`SpanStatus`** — `UNSET | OK | ERROR`, mirrors OpenTelemetry's status model.
- **`Event`** — `name`, `timestamp`, `attributes` — a point-in-time occurrence within
  a span (mirrors OTel span events).
- **`Span`** — `span_id`, `trace_id`, `parent_span_id`, `name`, `span_type`,
  `start_time`, `end_time`, `status`, `status_message`, `attributes`, `events`,
  `input`, `output`, `error` (`type`, `message`, `stacktrace`).
- **`Trace`** — `trace_id`, `name`, `start_time`, `end_time`, `status`, `tags`,
  `metadata`, `spans: list[Span]`.

These map 1:1 onto OpenTelemetry's trace/span/event concepts (trace_id, span_id,
parent_span_id, timestamps, attributes, events, status, exceptions) by design — see
section 8 for why PyAgentHound doesn't just *use* the OTel SDK in Phase 1.

## 4. Execution graph model (future — documented now per spec, not implemented)

A trace's spans already form a tree via `parent_span_id`. The **execution graph**
(Phase 2) is a superset of that tree: a directed graph where nodes are spans (or
external entities like documents/tools discovered via span attributes) and edges
carry a typed **relationship**, not just parent/child:

```
Node:  id, type, timestamp, duration, attributes, status
Edge:  source, destination, relationship

relationship ∈ {PARENT, CALLS, DEPENDS_ON, PRODUCES, CONSUMES,
                RETRIEVES, INVOKES, TRANSFORMS}
```

The graph is built by walking a trace's spans and, per `span_type`, extracting
additional nodes/edges from attributes (e.g. a `RETRIEVAL` span's `documents`
attribute produces `RETRIEVES` edges to per-document nodes — this is also the basis
for data/context lineage in section 13 of the product spec). The graph must be
queryable (by node type, by relationship, by time window) — the query interface is
designed once real usage from the finding/root-cause engines (Phase 3-4) exists,
rather than guessed at now.

## 5. Rule engine interface (future — documented now, not implemented)

Deterministic, not LLM-based. A rule is a pure function over a trace + its execution
graph that returns zero or more `Finding`s:

```python
class Rule(Protocol):
    id: str
    category: FailureCategory  # RETRIEVAL_FAILURE, TOOL_FAILURE, MODEL_FAILURE, ...

    def evaluate(self, trace: Trace, graph: ExecutionGraph,
                 baseline: Baseline | None) -> list[Finding]: ...
```

`Finding` fields (per product spec 6.5): `finding_id, category, severity, title,
description, evidence, affected_nodes, confidence, recommendation`. Rules run
independently and are individually unit-testable against fixture traces — this is
why the tracing model's attributes are unstructured dicts rather than per-span-type
subclasses: rules pattern-match on the attributes they care about and ignore the
rest, so adding a new AI-specific field never requires touching the core model.

The root-cause engine (Phase 4) consumes the list of `Finding`s plus graph structure
plus optional historical baseline and produces ranked hypotheses — explicitly labeled
"likely cause" / "contributing factor," never "truth," each with an evidence
reference and a confidence score whose components (evidence_strength,
temporal_correlation, causal_distance, historical_frequency, rule_confidence) are
exposed, not a single opaque number from an LLM.

## 6. Storage interfaces (Phase 1)

```python
class TraceStore(Protocol):
    def init_schema(self) -> None: ...
    def save_trace(self, trace: Trace) -> None: ...
    def get_trace(self, trace_id: str) -> Trace | None: ...
    def list_traces(self, limit: int = 50, offset: int = 0,
                     status: SpanStatus | None = None) -> list[TraceSummary]: ...
```

`SQLiteTraceStore` (`pyagenthound/storage/sqlite_store.py`) is the only Phase-1
implementation — zero-config local dev per the product spec's storage section. Two
tables, `traces` and `spans` (span `events`/`attributes`/`input`/`output` stored as
JSON text columns — a separate `events` table is unnecessary normalization for the
access patterns Phase 1 needs). The `TraceStore` Protocol exists specifically so a
`PostgresTraceStore` can be added later (multi-user/production deployments) without
any caller changing.

## 7. SDK API (Phase 1)

```python
from pyagenthound import AgentHound, SpanType

hound = AgentHound(endpoint="http://localhost:8787")  # or db_path=... for local-only

with hound.trace("customer-support-request") as trace:
    with trace.span("retrieval", span_type=SpanType.RETRIEVAL) as span:
        span.set_attribute("query", query)
        span.set_attribute("documents", documents)

@hound.trace("customer-support-request")
def handle_request(...): ...

@hound.span("retrieval", span_type=SpanType.RETRIEVAL)
def retrieve(...): ...
```

Current trace/span is tracked via `contextvars.ContextVar` (the same mechanism OTel
uses for context propagation), so `@hound.span` decorators nest correctly inside a
`with hound.trace(...)` block or another decorated function without manually passing
a trace/span object around. On `SpanContext.__exit__`, an uncaught exception sets
`status=ERROR` and calls `record_error()` automatically.

Export is local-first and split by whether `endpoint` is configured:
- No `endpoint` → `LocalSQLiteExporter` writes straight to `~/.pyagenthound/pyagenthound.db`.
- `endpoint` set → `HTTPExporter` POSTs to `{endpoint}/api/traces`; failures are
  caught and logged, never raised — instrumentation must never crash the host app.

Async/batched/sampled export (perf work) is **not implemented in Phase 1** — noted as
a known limitation rather than faked.

## 8. Why not just use the OpenTelemetry SDK directly?

The domain model is intentionally OTel-*compatible* (same core fields) so an
ingestion adapter can accept real OTel traces later (Phase 6) without a model change.
But taking a hard dependency on `opentelemetry-sdk` in Phase 1 would pull in exporter/
processor/resource abstractions PyAgentHound doesn't need yet, for a feature
(ingesting traces from other tools) nothing in Phase 1 uses. Phase 6 adds an adapter
that maps OTel spans → PyAgentHound `Span`s; it does not replace the native SDK.

## 9. API contract (Phase 1)

FastAPI app (`pyagenthound/api/app.py`), OpenAPI docs auto-served at `/docs`.

| Method | Path                | Purpose                                  |
|--------|---------------------|-------------------------------------------|
| POST   | `/api/traces`       | Ingest one completed trace (with spans)  |
| GET    | `/api/traces`       | List traces (`limit`, `offset`, `status`) |
| GET    | `/api/traces/{id}`  | Full trace detail with spans              |

Everything graph/findings/analyze/replay/evaluation-related from the product spec's
full API surface (section 19) is intentionally absent — those engines don't exist
yet, and an endpoint returning a stub payload would be worse than no endpoint.

## 10. Security / privacy boundaries (Phase 1 reality)

Phase 1 is local-only: SQLite file on disk, no auth, no network calls except the
optional HTTP export to a `pyagenthound serve` instance the developer is also running
locally. No redaction/PII-scrubbing engine exists yet (product spec sections 20-21) —
that is future work, not implemented as a no-op passthrough. What Phase 1 does
guarantee: the SDK/API never logs full attribute payloads at `INFO` or above, and
nothing is transmitted anywhere unless `endpoint` is explicitly set by the caller.
Configurable capture modes (metadata-only / full-content / hashed-content) are a
documented future capability, not built.

## 11. Testing strategy

- **Unit** — `tests/unit/`: model serialization round-trips, SDK context-manager/
  decorator nesting and error capture, SQLite store save/get/list round-trips.
- **Integration** — `tests/integration/`: FastAPI `TestClient` against a temp SQLite
  db (full ingest → list → get flow), CLI commands (`init`, `inspect`) against a
  fixture db.
- No test depends on a real external LLM API — there are none in Phase 1's scope, and
  this constraint carries forward as later phases add LLM-powered analysis.
