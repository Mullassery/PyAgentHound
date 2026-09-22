# PyAgentHound — Architecture

This document is the architecture deliverable for the project: it identifies MVP
boundaries, core domain models, API contracts, the execution-graph model, the rule
engine, the root-cause engine, storage interfaces, the SDK API, security/privacy
boundaries, and testing strategy. Sections marked **(built)** or with a specific
Phase are implemented today. Sections marked **(future)** describe the intended
contract so later phases build against a stable shape, not because the code exists
yet — see `ROADMAP_HONEST.md` for exactly what's real right now.

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

## 2. MVP boundary (Phase 1-4)

Phase 1 delivered the substrate everything else builds on: capture a trace, store it,
retrieve it, look at it. Phase 2 added the execution graph — spans plus their
attribute-derived entities (documents, for now) assembled into a queryable directed
graph. Phase 3 added a deterministic rule engine that evaluates findings over that
graph — the first component that actually *detects* something, rather than just
recording it. Phase 4 added a root-cause engine that ranks findings into a "likely
cause" plus "contributing factors" — but only the confidence-model components that
don't require historical data (see section 6); temporal correlation and historical
frequency stay unimplemented until baseline storage exists. Still no web UI, no
replay, no eval, no historical baselines. Concretely, Phase 1-4 = SDK + tracing model
+ SQLite storage + execution graph + rule engine (5 built-in rules) + root-cause
ranking + a 6-endpoint API + a 4-command CLI. See `ROADMAP_HONEST.md` for the
authoritative built-vs-not list.

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
section 9 for why PyAgentHound doesn't just *use* the OTel SDK in Phase 1.

## 4. Execution graph model (Phase 2 — built)

A trace's spans already form a tree via `parent_span_id`. The **execution graph**
is a superset of that tree: a directed graph where nodes are spans (or external
entities like documents discovered via span attributes) and edges carry a typed
**relationship**, not just parent/child:

```
Node:  id, type, name, timestamp, duration_ms, attributes, status
Edge:  source, target, relationship

relationship ∈ {PARENT, CALLS, DEPENDS_ON, PRODUCES, CONSUMES,
                RETRIEVES, INVOKES, TRANSFORMS}
```

`pyagenthound/graph/models.py` — `NodeType` (span types + `TRACE` for the synthetic
per-trace root node + `DOCUMENT` for extracted lineage entities), `Relationship`,
`Node`, `Edge`, `ExecutionGraph`. `ExecutionGraph` is queryable: `nodes_by_type`,
`edges_by_relationship`, `nodes_in_window`, `outgoing`/`incoming`/`neighbors`, and
`ancestors` (transitive backward walk — the basis for data/context lineage,
product spec section 13).

`pyagenthound/graph/builder.py` — `build_graph(trace)` creates the `TRACE` root node
and one node per span, linked by `PARENT` edges (a span with a `parent_span_id` not
present in the trace attaches to the trace root rather than being dropped). On top of
that structural tree, a small per-`SpanType` extractor registry (`@_register(...)`)
pulls additional nodes/edges out of span attributes. **Phase 2 ships exactly one
extractor**: `RETRIEVAL` spans with a `documents` attribute produce `DOCUMENT` nodes
+ `RETRIEVES` edges — this is the literal mechanism behind the stale-document demo
scenario (product spec section 27) once the finding engine (Phase 3) exists to reason
over it. Extractors for other span types (tool arguments, MCP resources, embedding
inputs, etc.) are a documented future extension via the same registry pattern — not
built yet, not stubbed.

Exposed via `GET /api/traces/{id}/graph` (section 10).

## 5. Rule engine (Phase 3 — built)

Deterministic, not LLM-based. A rule is a pure function over a trace + its execution
graph that returns zero or more `Finding`s (`pyagenthound/rules/models.py`):

```python
class Rule(Protocol):
    id: str
    category: FailureCategory  # RETRIEVAL_FAILURE, TOOL_FAILURE, MODEL_FAILURE, ...

    def evaluate(self, trace: Trace, graph: ExecutionGraph) -> list[Finding]: ...
```

No `baseline` parameter yet — historical-baseline-aware rules are Phase 4 work (the
signature will grow then, deliberately not accepting an always-`None` placeholder
today). `Finding` fields (per product spec 6.5): `finding_id, rule_id, category,
severity, title, description, evidence, affected_nodes, confidence, recommendation`.
Rules run independently and are individually unit-testable against fixture traces —
this is why the tracing model's attributes are unstructured dicts rather than
per-span-type subclasses: rules pattern-match on the attributes they care about and
ignore the rest, so adding a new AI-specific field never requires touching the core
model.

`pyagenthound/rules/engine.py` — `DEFAULT_RULES` + `run_rules(trace, graph, rules=None)`
evaluates every registered rule and concatenates their findings. **Five built-in
rules ship in Phase 3** (`pyagenthound/rules/builtin.py`), chosen to prove the pattern
across more than one `FailureCategory` rather than exhaustively covering the product
spec's full rule list (section 6.5):

- `empty_retrieval` (RETRIEVAL_FAILURE) — a `RETRIEVAL` span whose `documents`
  attribute is an empty list.
- `stale_retrieval_documents` (RETRIEVAL_FAILURE) — within one retrieval, documents
  whose `date` attribute predates the most recently dated document retrieved for the
  same query. This is the deterministic signal behind the stale-context demo scenario
  (product spec section 27); it compares dates *within* a single retrieval, not
  against an external "active version" baseline (no such baseline exists until
  Phase 4).
- `duplicate_retrieved_documents` (RETRIEVAL_FAILURE) — repeated document ids in one
  retrieval's results.
- `tool_failure` (TOOL_FAILURE) — a `TOOL`/`MCP` span that ended with `status=ERROR`.
- `dangling_parent_span` (CONFIGURATION_FAILURE) — a span whose `parent_span_id`
  isn't present in the trace (the same condition `build_graph` falls back to
  attaching at the trace root for, surfaced here as an anomaly worth a human look).

The remaining rules from product spec section 6.5 (empty/low-relevance retrieval
nuances, prompt/model change detection, token explosion, tool/agent loops, schema
violations, etc.) are documented future work in `ROADMAP_HONEST.md`, addable the same
way: a class with `id`/`category`/`evaluate`, appended to `DEFAULT_RULES`.

Exposed via `POST /api/traces/{id}/analyze` (section 10) and `pyagenthound analyze`.
A `Finding.confidence` is only the rule's own certainty about its specific anomaly —
see section 6 for how that becomes a root-cause confidence.

## 6. Root-cause engine (Phase 4 — built, partial)

Consumes the list of `Finding`s plus the execution graph and ranks them into
hypotheses, explicitly labeled — never "truth" (`pyagenthound/rootcause/`):

```python
class ConfidenceComponents(BaseModel):
    evidence_strength: float          # = the underlying Finding's own confidence
    causal_proximity: float           # graph-distance to the trace's final-output span
    temporal_correlation: float | None = None   # Phase 4b (historical baselines) — not computed
    historical_frequency: float | None = None   # Phase 4b (historical baselines) — not computed

class RootCauseHypothesis(BaseModel):
    hypothesis_id: str
    finding_id: str
    rule_id: str
    category: FailureCategory
    label: str  # "likely_cause" | "contributing_factor"
    statement: str
    evidence: list[Evidence]
    affected_nodes: list[str]
    confidence: float
    confidence_components: ConfidenceComponents
    recommendation: str | None
```

`rank_root_causes(trace, graph, findings=None)` turns each `Finding` into exactly one
`RootCauseHypothesis` (calling `run_rules` itself if `findings` isn't passed in),
computes its confidence from the **two components that are honestly computable
today**, sorts by confidence descending, and labels the top hypothesis
`likely_cause` — everything else is `contributing_factor`:

- **`evidence_strength`** — the originating `Finding.confidence` directly.
- **`causal_proximity`** — how many `PARENT`-edge hops separate the finding's span
  from the span with the latest `end_time` in the trace (a proxy for "the span that
  produced the final output"). Computed by walking the execution graph's `PARENT`
  edges upward from the final span until either the finding's span is reached (score
  `1/(1+hops)`) or the walk exhausts without finding it (fixed low score `0.3` — the
  finding is real, just not on the path to the final output, e.g. a parallel branch).
- **`temporal_correlation`** and **`historical_frequency`** are left `None` — they
  require historical baseline storage (product spec section 6.8), which doesn't
  exist yet. Exposing a fabricated number for either would be worse than omitting
  them; the overall `confidence` formula only ever combines the two real components
  (`0.7 * evidence_strength + 0.3 * causal_proximity`). This is why Phase 4 is marked
  "built, partial" rather than "built" — the confidence model exists and is honest
  about what it does and doesn't account for, but two of its five documented
  components (product spec section 6.7) are not implemented.

No fabricated "observed consequence" (e.g. "incorrect answer") is generated — that
would require ground truth about correctness, which nothing in this system has.

Exposed via `GET /api/traces/{id}/root-cause` (section 10) and included in
`pyagenthound analyze`'s output, after the raw findings.

## 7. Storage interfaces (Phase 1)

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

## 8. SDK API (Phase 1)

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

## 9. Why not just use the OpenTelemetry SDK directly?

The domain model is intentionally OTel-*compatible* (same core fields) so an
ingestion adapter can accept real OTel traces later (Phase 6) without a model change.
But taking a hard dependency on `opentelemetry-sdk` in Phase 1 would pull in exporter/
processor/resource abstractions PyAgentHound doesn't need yet, for a feature
(ingesting traces from other tools) nothing in Phase 1 uses. Phase 6 adds an adapter
that maps OTel spans → PyAgentHound `Span`s; it does not replace the native SDK.

## 10. API contract (Phase 1-4)

FastAPI app (`pyagenthound/api/app.py`), OpenAPI docs auto-served at `/docs`.

| Method | Path                           | Purpose                                     |
|--------|--------------------------------|------------------------------------------------|
| POST   | `/api/traces`                  | Ingest one completed trace (with spans)     |
| GET    | `/api/traces`                  | List traces (`limit`, `offset`, `status`)   |
| GET    | `/api/traces/{id}`             | Full trace detail with spans                |
| GET    | `/api/traces/{id}/graph`       | Execution graph for the trace (section 4)   |
| POST   | `/api/traces/{id}/analyze`     | Run the deterministic rule engine, return `list[Finding]` (section 5) |
| GET    | `/api/traces/{id}/root-cause`  | Ranked `list[RootCauseHypothesis]` (section 6) |

`root-cause` as a separate `GET` endpoint (rather than folding it into `analyze`) is
a deliberate deviation from the product spec's endpoint list (section 19), which
predates findings and root-cause hypotheses being distinct concerns in this
codebase — keeping them separate avoided a breaking change to `analyze`'s already-
tested response shape. Replay/evaluation-related endpoints are intentionally absent
— those engines don't exist yet, and an endpoint returning a stub payload would be
worse than no endpoint.

## 11. Security / privacy boundaries (Phase 1 reality)

Phase 1 is local-only: SQLite file on disk, no auth, no network calls except the
optional HTTP export to a `pyagenthound serve` instance the developer is also running
locally. No redaction/PII-scrubbing engine exists yet (product spec sections 20-21) —
that is future work, not implemented as a no-op passthrough. What Phase 1 does
guarantee: the SDK/API never logs full attribute payloads at `INFO` or above, and
nothing is transmitted anywhere unless `endpoint` is explicitly set by the caller.
Configurable capture modes (metadata-only / full-content / hashed-content) are a
documented future capability, not built.

## 12. Testing strategy

- **Unit** — `tests/unit/`: model serialization round-trips, SDK context-manager/
  decorator nesting and error capture, SQLite store save/get/list round-trips, graph
  construction (parent tree, dangling-parent fallback, the `RETRIEVAL` extractor,
  query methods including `ancestors`), each of the 5 built-in rules (positive and
  negative case) plus `run_rules` aggregation, root-cause ranking (causal proximity
  at varying graph depths, `likely_cause` vs `contributing_factor` labeling).
- **Integration** — `tests/integration/`: FastAPI `TestClient` against a temp SQLite
  db (full ingest → list → get → graph → analyze → root-cause flow), CLI commands
  (`init`, `inspect`, `analyze`) against a fixture db.
- No test depends on a real external LLM API — there are none in Phase 1's scope, and
  this constraint carries forward as later phases add LLM-powered analysis.
