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

## 2. MVP boundary (Phase 1-9)

Phase 1 delivered the substrate everything else builds on: capture a trace, store it,
retrieve it, look at it. Phase 2 added the execution graph — spans plus their
attribute-derived entities (documents, for now) assembled into a queryable directed
graph. Phase 3 added a deterministic rule engine that evaluates findings over that
graph — the first component that actually *detects* something, rather than just
recording it. Phase 4 added a root-cause engine that ranks findings into a "likely
cause" plus "contributing factors". Phase 5 added historical baselines — comparing a
trace against the most recent prior successful execution of the same named workflow,
which completes the confidence model's remaining two components
(`temporal_correlation`, `historical_frequency`) for findings where comparable
history exists. Phase 6 added replay — clone a trace, override span attributes,
re-run the finding engine, and see whether the anomaly clears (section 13). Phase 7
added evaluation — declarative assertions about a trace, run as a CI-gateable test
suite (section 14). Phase 8 added a server-rendered web UI (section 15) exposing all
of the above visually — requests list, request detail with an interactive execution
graph, findings, root-cause hypotheses, and a replay form. Phase 9 added an optional
LLM-powered explanation layer (section 16) that narrates findings/hypotheses in
plain English, strictly grounded in the evidence already computed — verified against
a real local Ollama model, not a mock. Concretely, Phase 1-9 = SDK + tracing model +
SQLite storage + execution graph + rule engine (5 built-in rules) + root-cause
ranking + historical baseline comparison + replay + file-based evaluation + a web UI
+ an optional LLM explanation layer + an 8-endpoint API + a 6-command CLI. See
`ROADMAP_HONEST.md` for the authoritative built-vs-not list.

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
`finding_id` is a **deterministic** hash of `rule_id` + `affected_nodes` (fixed in
Phase 9 after it was found to be a random UUID — see section 16 — which broke
`finding_id` as a stable reference across separate `run_rules()` calls over the same
trace); two calls over identical trace data always produce identical ids for the
same logical finding, even though findings are never persisted and are always
recomputed from scratch. Rules run independently and are individually unit-testable
against fixture traces —
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

## 6. Root-cause engine + historical baselines (Phase 4-5 — built)

Consumes the list of `Finding`s plus the execution graph (and, when a `TraceStore`
is available, historical data from other traces) and ranks them into hypotheses,
explicitly labeled — never "truth" (`pyagenthound/rootcause/`):

```python
class ConfidenceComponents(BaseModel):
    evidence_strength: float
    causal_proximity: float
    temporal_correlation: float | None = None    # only set when a baseline exists
    historical_frequency: float | None = None    # only set when comparable history exists

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

`rank_root_causes(trace, graph, findings=None, store=None)` turns each `Finding` into
exactly one `RootCauseHypothesis`, sorts by confidence descending, and labels the top
hypothesis `likely_cause` — everything else is `contributing_factor`. All four
confidence components are implemented; only the last two are conditional on data that
doesn't always exist:

- **`evidence_strength`** — the originating `Finding.confidence` directly.
- **`causal_proximity`** — how many `PARENT`-edge hops separate the finding's span
  from the span with the latest `end_time` in the trace (a proxy for "the span that
  produced the final output"). Computed by walking the execution graph's `PARENT`
  edges upward from the final span until either the finding's span is reached (score
  `1/(1+hops)`) or the walk exhausts without finding it (fixed low score `0.3` — the
  finding is real, just not on the path to the final output, e.g. a parallel branch).
- **`temporal_correlation`** — set to `1.0` for findings produced by baseline
  comparison (see below), since those are by construction about a change between
  temporally adjacent executions; `None` for ordinary rule-engine findings, which
  have no "before/after" framing within a single trace.
- **`historical_frequency`** — fraction of recent same-named traces where this exact
  `rule_id` also fired (`historical_rule_frequencies`, below); `None` when `store`
  isn't passed or no comparable history exists. A high frequency means the anomaly
  is a recurring, familiar pattern — it is **not** by itself evidence that the
  pattern is the correct root cause for *this* failure.

Overall confidence is a weighted average over whichever components are present
(`_combine_confidence`), weights `{evidence_strength: 0.4, causal_proximity: 0.2,
temporal_correlation: 0.2, historical_frequency: 0.2}`, renormalized over the
non-`None` subset — e.g. with only the first two present, confidence is
`(0.4 × evidence_strength + 0.2 × causal_proximity) / 0.6`.

No fabricated "observed consequence" (e.g. "incorrect answer") is generated — that
would require ground truth about correctness, which nothing in this system has.

**Historical baselines** (`pyagenthound/baseline/`, product spec section 6.8):

- `extract_signature(trace) -> ExecutionSignature` — a comparable summary: model,
  prompt version, retriever, tools invoked, latency, token usage, execution path
  (the ordered sequence of span types).
- `find_baseline(store, trace)` — the most recent prior execution with `status=OK`
  and the same `trace.name` (used as the "same logical workflow" key — a documented
  heuristic, not semantic understanding of what the trace does).
- `compare_to_baseline(trace, baseline) -> list[Finding]` — diffs the two signatures
  and emits a `Finding` per changed field (`baseline_model_changed`,
  `baseline_prompt_changed`, `baseline_retriever_changed`, `baseline_tools_changed`,
  `baseline_execution_path_changed`, `baseline_latency_regression` /
  `baseline_token_growth` for >1.5x numeric increases). Every description explicitly
  states this is "an observed change, not a claim that it caused the current
  outcome" — matching the product spec's "do not automatically claim causality."
- `historical_rule_frequencies(store, trace)` — runs the stateless rule engine
  against recent same-named traces (any status) and reports what fraction also
  produced each `rule_id`, in one pass per historical trace (not per current
  finding) to keep cost linear rather than quadratic.

Exposed via `GET /api/traces/{id}/root-cause` (section 10, `store`-aware) and
included in `pyagenthound analyze`'s output, after the raw findings — which also get
baseline-comparison findings merged in when a baseline exists.

## 7. Storage interfaces (Phase 1, extended Phase 5)

```python
class TraceStore(Protocol):
    def init_schema(self) -> None: ...
    def save_trace(self, trace: Trace) -> None: ...
    def get_trace(self, trace_id: str) -> Trace | None: ...
    def list_traces(self, limit: int = 50, offset: int = 0, status: SpanStatus | None = None,
                     name: str | None = None) -> list[TraceSummary]: ...
```

`name` was added in Phase 5 specifically so `find_baseline`/`historical_rule_frequencies`
(section 6) can filter to "prior executions of this same logical workflow" with a real
SQL `WHERE`, instead of over-fetching and filtering in Python.

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

## 10. API contract (Phase 1-9)

FastAPI app (`pyagenthound/api/app.py`), OpenAPI docs auto-served at `/docs`.

| Method | Path                           | Purpose                                     |
|--------|--------------------------------|------------------------------------------------|
| POST   | `/api/traces`                  | Ingest one completed trace (with spans)     |
| GET    | `/api/traces`                  | List traces (`limit`, `offset`, `status`, `name`) |
| GET    | `/api/traces/{id}`             | Full trace detail with spans                |
| GET    | `/api/traces/{id}/graph`       | Execution graph for the trace (section 4)   |
| POST   | `/api/traces/{id}/analyze`     | Run the deterministic rule engine + baseline comparison, return `list[Finding]` (sections 5-6) |
| GET    | `/api/traces/{id}/root-cause`  | Ranked `list[RootCauseHypothesis]` (section 6), baseline-aware |
| POST   | `/api/traces/{id}/replay`      | Clone + override + re-analyze, return `ReplayResult` (section 13); `409` if an unconfirmed non-`READ_ONLY` override is requested |
| POST   | `/api/traces/{id}/explain`     | Optional LLM narrative over existing findings/hypotheses, return `LLMExplanation` (section 16); `400` if there are no findings to explain, `503` if the provider is unreachable, `422` if its output fails evidence-grounding validation |

`root-cause` as a separate `GET` endpoint (rather than folding it into `analyze`) is
a deliberate deviation from the product spec's endpoint list (section 19), which
predates findings and root-cause hypotheses being distinct concerns in this
codebase — keeping them separate avoided a breaking change to `analyze`'s already-
tested response shape. Evaluation has no API endpoint by design (section 14) —
test cases are file-based, meant to be committed to version control and run by
`pyagenthound test` in CI, not served.

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
  decorator nesting and error capture, SQLite store save/get/list round-trips (incl.
  the `name` filter), graph construction (parent tree, dangling-parent fallback, the
  `RETRIEVAL` extractor, query methods including `ancestors`), each of the 5
  built-in rules (positive and negative case) plus `run_rules` aggregation,
  root-cause ranking (causal proximity at varying graph depths, `likely_cause` vs
  `contributing_factor` labeling, the weighted confidence combiner with 2 vs 4
  components present), baseline signature extraction/comparison (each change type)
  and historical rule frequency computation, replay (safety classification defaults,
  plan confirmation logic, clone-with-overrides id remapping, a real
  finding-resolves-after-override case), each of the 5 assertion types plus JSON
  save/load round-trips, `finding_id` determinism (two separate `run_rules()` calls
  over the identical trace produce identical ids — section 16's regression test),
  and LLM explanation validation against a fake, deterministic provider (grounded
  citation accepted; invalid JSON, missing fields, non-string citations, and an
  unsupported `finding_id` each independently rejected).
- **Integration** — `tests/integration/`: FastAPI `TestClient` against a temp SQLite
  db (full ingest → list → get → graph → analyze → root-cause → replay → explain
  flow, plus a two-trace baseline scenario verifying `temporal_correlation` gets
  set, a `409` on an unconfirmed unsafe replay override, and `400`/`503` explain
  error paths with a fake/unavailable provider), CLI commands (`init`, `inspect`,
  `analyze` with and without a baseline or `--explain`, `replay` with and without an
  unsafe override, `test` against passing/failing/missing-trace/empty-directory
  cases) against a fixture db, and the web UI (`test_ui.py`: requests list
  empty/populated/filtered states, request-detail rendering asserted against real
  finding/root-cause text, the graph script tag's `data-trace-id`, and the replay
  form's POST → 303 redirect — both the success path to the new replayed trace and
  the `?replay_error=` path for an unconfirmed unsafe override). The full UI was
  also driven in a real browser (not just `TestClient`) — see section 15 for what
  that verified.
- **LLM integration** (`tests/integration/test_llm_real_ollama.py`) — the one
  intentional exception to "no test depends on an external LLM API" (product spec
  section 28): `explain_root_cause` against a genuinely running local Ollama,
  auto-`skipif` when Ollama isn't reachable on `localhost:11434`. Never a paid
  cloud API — this only ever talks to localhost.
- No test depends on a real external LLM API — there are none in Phase 1's scope, and
  this constraint carries forward as later phases add LLM-powered analysis.

## 13. Replay (Phase 6 — built)

PyAgentHound observes traces; it does not own the agent's runtime. It cannot
honestly "call the LLM again" or "re-run the tool" — it has no API keys, no access to
the original function, often not even the original process. What it *can* do
honestly: clone a captured trace, apply attribute overrides to specific spans (a
counterfactual edit of already-captured data), and re-run the finding engine to see
whether the anomaly clears. This is the literal mechanism behind the product spec's
demo workflow (section 27): "fix retrieval, replay, see it resolved" — "fixing
retrieval" here means overriding the `RETRIEVAL` span's `documents` attribute to
what a corrected retriever *would* have returned, not actually querying a vector DB
again.

`pyagenthound/replay/`:

```python
class SafetyLevel(str, Enum):
    READ_ONLY = "READ_ONLY"
    WRITE = "WRITE"
    DESTRUCTIVE = "DESTRUCTIVE"
    UNKNOWN = "UNKNOWN"

class ReplayResult(BaseModel):
    original_trace_id: str
    replayed_trace_id: str
    plan: ReplayPlan
    original_findings: list[Finding]
    replayed_findings: list[Finding]
    resolved_rule_ids: list[str]   # fired on the original, not on the replay
    new_rule_ids: list[str]        # fired on the replay, not on the original
```

- `classify_span_safety(span)` — an explicit `span.attributes["safety"]` (set by the
  developer at capture time) wins; otherwise only `RETRIEVAL`, `EMBEDDING`,
  `RERANKING`, `LLM`, `PROMPT` default to `READ_ONLY` — every other span type
  (`TOOL`, `MCP`, `API`, `DATABASE`, `MEMORY`, ...) defaults to `UNKNOWN`.
  Conservative on purpose: an unannotated span is never assumed safe.
- `build_plan(trace, overrides)` — a `ReplayStep` per span with its safety
  classification and any proposed overrides; `ReplayPlan.requires_confirmation` is
  true iff any *overridden* step's safety isn't `READ_ONLY`.
- `apply_overrides(trace, overrides)` — clones the trace with fresh trace/span ids
  (a real, separate, independently-inspectable trace — not a diff object) and merges
  the given per-original-span-id attribute dict into each cloned span's attributes.
  Tagged `"replay"`, with `metadata["replayed_from"]` pointing at the source trace.
- `run_replay(store, trace, overrides, allow_unsafe=False)` — builds the plan; if it
  `requires_confirmation` and `allow_unsafe` is false, raises `UnsafeReplayError`
  (mapped to HTTP 409 by the API, a `ClickException` by the CLI) rather than silently
  proceeding. Otherwise runs the rule engine on both the original and the replayed
  trace, saves the replayed trace to the store (so it's inspectable like any other
  trace), and returns the finding-set diff.

Exposed via `POST /api/traces/{id}/replay` (section 10) and `pyagenthound replay
<trace_id> --set NAME.KEY=VALUE [--allow-unsafe]`. Verified end to end against the
actual stale-document scenario: overriding the `retrieval` span's `documents` to
just the current policy version resolved `stale_retrieval_documents` (1 finding → 0)
— real CLI/API output, not a scripted demo.

Not built: re-invoking a live model/tool/retriever (would require the developer's
own callable, which the current design doesn't accept — a documented future
extension, not a limitation of the safety model itself), replaying against a
different model/prompt *by calling it* (only by overriding the recorded attribute,
which changes what the finding engine sees but not what any downstream system
receives).

## 14. Evaluation / regression testing (Phase 7 — built)

A test case is a declarative set of assertions about an already-captured trace, not
a way to re-invoke the agent under different conditions (see section 13 for why
PyAgentHound can't do that honestly). The intended loop: capture a trace, run
`pyagenthound analyze` to see what's true about it, hand-author a small JSON file
asserting the properties that should hold, commit it, and run `pyagenthound test
./tests` in CI on every change (`pyagenthound test` exits non-zero if any assertion
fails, for CI gating — product spec section 15).

`pyagenthound/evaluation/`:

```python
class AssertionType(str, Enum):
    STATUS_OK = "STATUS_OK"
    OUTPUT_CONTAINS = "OUTPUT_CONTAINS"
    NO_FINDING = "NO_FINDING"
    SPAN_EXISTS = "SPAN_EXISTS"
    NO_TOOL_CALLED = "NO_TOOL_CALLED"

class Assertion(BaseModel):
    type: AssertionType
    target: str | None = None   # substring / rule_id-or-category / span name / tool name

class TestCase(BaseModel):
    name: str
    trace_id: str
    assertions: list[Assertion]
```

Example test case file (hand-authored, this is the real JSON shape — not a schema
sketch):

```json
{
  "name": "cancellation_policy_mentions_window",
  "trace_id": "cf8f6b96514d4e1e89c946e7140b2d5b",
  "assertions": [
    {"type": "STATUS_OK", "target": null},
    {"type": "OUTPUT_CONTAINS", "target": "cancel"},
    {"type": "NO_FINDING", "target": "stale_retrieval_documents"},
    {"type": "NO_TOOL_CALLED", "target": "charge_card"}
  ]
}
```

`evaluate(trace, findings, test_case) -> TestCaseResult` checks each assertion —
`NO_FINDING` runs the real rule engine's output against a `rule_id` or
`FailureCategory` value, not a stubbed check. Test cases are stored as JSON files on
disk (`pyagenthound/evaluation/io.py`: `save_test_case`/`load_test_case`/
`load_test_cases`), not in the trace database — they're meant to be committed to
version control like any other test fixture, which is also why there is **no API
endpoint** for evaluation (a deliberate scope decision, section 10): `GET
/api/evaluations` from the product spec's full surface (section 19) would need
either server-side test-case storage or a way to point the server at a filesystem
path, neither of which is worth the complexity for a CLI/CI-shaped feature.

`pyagenthound test <tests_dir> [--db]` loads every `*.json` in `tests_dir`, looks up
each referenced `trace_id` in the database, runs the rule engine, evaluates
assertions, prints PASS/FAIL per test case with the specific failing assertions, and
exits `1` if anything failed or a referenced trace is missing. Verified end to end:
a passing test case against a real trace, then pointed at a real regressed trace
(stale documents reintroduced) — correctly flips to FAIL with the exact assertion
that broke (`NO_FINDING('stale_retrieval_documents')`) and a non-zero exit code.

Not built: a `pyagenthound test create` scaffolding command (hand-authoring the
small JSON is a reasonable MVP burden — this is documented future work, not a
missing essential), running the same test case against multiple models/prompts
side by side (product spec section 15's "run against model A / model B" — requires
live re-invocation, same gap as replay), assertion types beyond the 5 above.

## 15. Web UI (Phase 8 — built)

Server-rendered (FastAPI + Jinja2), not a JS single-page app — no npm/build step,
consistent with "Python is the primary developer API" (README design principles;
also avoids "unnecessary infrastructure," product spec section 15/37). The one place
vanilla JS is used at all is the execution graph, and even that is a thin client of
the existing `GET /api/traces/{id}/graph` JSON endpoint (section 10) — the UI never
re-implements graph construction, it fetches the same data the API already serves
and lays it out client-side.

`pyagenthound/ui/`:
- `routes.py` — `GET /` (requests list, `name`/`status` query-param filters),
  `GET /requests/{id}` (the consolidated request-detail view), `POST
  /requests/{id}/replay` (a single `NAME.KEY=VALUE` text field + an "allow unsafe"
  checkbox, calling the same `run_replay` the CLI/API use, redirecting to the
  replayed trace's own detail page on success or back with `?replay_error=` on an
  `UnsafeReplayError`).
- `templates/` — `base.html`, `requests_list.html`, `request_detail.html`. Pydantic
  model instances (`Trace`, `Finding`, `RootCauseHypothesis`, `ExecutionSignature`)
  are passed straight into the Jinja context and accessed via normal attribute
  syntax (`trace.status.value`, `finding.severity.value`) — no extra serialization
  layer.
- `static/style.css` — a small hand-written stylesheet, dark-mode aware via
  `prefers-color-scheme`, no CSS framework.
- `static/graph.js` — fetches the graph JSON, computes a simple BFS-from-root level
  layout (nodes grouped into rows by hop-distance from the `TRACE` root, positioned
  evenly within their row), renders boxes + curved edges as SVG, and shows a node's
  full attributes on click. No charting/graph library — the graphs here are small
  (one trace's worth of spans) and don't need a force-directed layout engine.

**Deliberate scope cut from the product spec's nav (section 17):** one consolidated
request-detail page instead of separate "Findings," "Graph," "Evaluations," and
"Replays" top-level pages. The spec's own Request-page description already lists
metadata/findings/graph/timeline/root-cause/replay together under one view; splitting
them into separate top-level nav items would fragment a single request's story
across five pages for no benefit at this scale. No "Overview" dashboard and no
"Settings" page either — both would be hollow placeholders today (no cross-request
aggregate stats worth showing yet, no configurable settings to expose), and building
an empty page to satisfy a nav list would be exactly the kind of stub the no-fake-
stubs policy rules out.

Verified in a real browser (not just `TestClient`): requests list renders with dark
mode, execution graph is genuinely interactive (click any node — including a
`DOCUMENT` leaf — and its real attributes show up in the detail panel), and the full
replay loop works end to end — submitting `retrieval.documents=[{"id":
"policy-2026", ...}]` through the form redirects to a new request page tagged
"Replayed from `<original>`" whose Findings count visibly drops (4 → 3) with
`stale_retrieval_documents` gone, exactly matching the CLI/API behavior from
section 13.

Not built: an `Overview` dashboard, a `Settings` page, authentication (the API
server has none — section 11 — and neither does the UI), a JS-driven live-updating
requests list (the list is a plain server-rendered page, reloaded on navigation).

## 16. LLM-powered analysis (Phase 9 — built)

Strictly additive and opt-in — design principles 7-8 ("make the system useful
without an LLM," "LLM-powered analysis should be optional"). This layer never
detects anything new and never replaces the deterministic rule/root-cause engines;
it only asks a model to narrate, in plain English, findings and hypotheses those
engines already computed. The model is shown **only** the structured evidence —
`finding_id`, category, severity, title, description, evidence descriptions,
confidence, recommendation per finding; label/statement/`finding_id`/confidence per
hypothesis — never the raw trace, never asked to produce its own confidence number.

`pyagenthound/llm/`:

```python
class LLMProvider(Protocol):
    name: str
    def complete(self, system: str, user: str) -> str: ...
```

Provider-neutral by design (product spec sections 1/25), but **only `OllamaProvider`
is implemented** — local, no API key, no network egress beyond localhost, matching
"local-first development should be possible." OpenAI/Anthropic providers would
implement the same three-line Protocol; not built, because there's no way to verify
them without paid API keys in this environment, and an unverified provider
implementation would be worse than none (`no-fake-stubs` policy).

`explain_root_cause(findings, hypotheses, provider) -> LLMExplanation` builds a
strict prompt instructing the model to respond with **only** JSON —
`{"narrative": "...", "cited_finding_ids": [...]}` — then validates the response
before returning anything: invalid JSON, a missing field, or (critically) any
`finding_id` in `cited_finding_ids` that doesn't exist in the findings it was given
all raise `LLMOutputValidationError` rather than being silently accepted or
corrected. This is the concrete implementation of product spec section 7's "reject
unsupported claims" — not a comment, an enforced check with its own test coverage.
`LLMUnavailableError` (provider unreachable, e.g. Ollama not running) is a distinct,
separately-handled failure — both fail *soft* at the call sites: `pyagenthound
analyze --explain` prints the deterministic output regardless and only adds a short
"unavailable" or "rejected" line if the LLM step fails; `POST /api/traces/{id}/explain`
returns `503`/`422` respectively rather than a 500.

**Bug found and fixed while building this** (`pyagenthound/rules/models.py`):
`Finding.finding_id` was a random UUID generated fresh on every `Finding`
construction. Findings aren't persisted — every `analyze`/`root-cause`/`explain`
call recomputes them from the trace — so two separate `run_rules()` calls over the
*identical* trace produced *different* ids for what is logically the same finding.
This was invisible until this phase needed a `finding_id` to stay stable as a cross-
call reference (the LLM citing one, the CLI printing the deterministic sections
using a *different* internally-recomputed set) — surfaced immediately as citation-
validation test failures. Fixed by making `finding_id` a deterministic hash of
`rule_id` + `affected_nodes` instead of random (`model_validator(mode="after")`);
regression test (`test_finding_id_is_deterministic_across_repeated_runs`) asserts
two separate `run_rules()` calls produce identical ids. Verified live: the CLI and a
separately-started `pyagenthound serve` process, running against the same trace,
independently computed and returned the exact same `finding_id`.

Verified end to end against a real local `qwen2.5:7b-instruct` (via Ollama, no
network egress beyond localhost) on the stale-document scenario — genuine,
unedited narrative: *"The retrieval process is returning outdated document
versions, as two out of three retrieved documents predate the newest version,"*
citing the real finding id, via both `pyagenthound analyze --explain` and
`POST .../explain`.

Not built: OpenAI/Anthropic/other cloud providers (see above), any caching of LLM
output, streaming responses, an LLM-suggested-fix-then-auto-replay loop.
