# PyAgentHound

**Evidence-based debugging and root-cause analysis for AI agents and LLM applications.**

> **Status: Phase 1-7 MVP.** Trace capture, storage, inspection, a queryable execution
> graph, a deterministic rule engine (5 built-in rules), root-cause ranking,
> historical baseline comparison, safe replay, and file-based evaluation/regression
> testing work end to end and are tested. LLM-powered analysis and a web UI described
> below in "Where this is going" are **not built yet** — see
> [`ROADMAP_HONEST.md`](ROADMAP_HONEST.md) for the exact built-vs-not line.

## The problem

Traditional observability tells you *what happened*:

```
request failed
API returned 500
latency = 4.2s
```

That's not enough for AI systems, which fail in AI-shaped ways: retrieval returned
stale documents, the wrong tool got selected, a prompt changed and nobody noticed,
the model's context was silently truncated. Debugging that today means manually
reading through logs and hoping you spot the anomaly.

PyAgentHound's job is to answer a more specific question:

> **Why did my AI application produce this result?**

not just "what happened during this request?" — by capturing execution evidence
across the full path (request → agent → prompt → retriever → vector DB → tools/MCP →
model → response), assembling it into a causal execution graph, and running analysis
over that graph.

## How it finds root causes

Every finding distinguishes **observed facts** from **detected anomalies** from
**inferred causes** from **recommendations** — an inference is never presented as a
fact, and every conclusion carries an evidence reference. See
[`docs/architecture.md`](docs/architecture.md) for the full design.

What's real today — `pyagenthound analyze <trace_id>` against a trace with three
retrieved policy documents (2024/2025/2026 versions):

```
HIGH  Retrieved documents include stale versions
  2 of 3 dated documents retrieved by 'retrieval' predate the most recently
  dated document retrieved for the same query.
  evidence: document policy-2024 dated 2024-01-01, newest retrieved is dated 2026-01-01
  confidence: 0.95

Root Cause Analysis (deterministic estimate, not verified truth)

Likely cause: Retrieved documents include stale versions
  confidence: 0.73  (evidence_strength=0.95, causal_proximity=0.30)
  recommendation: Add a freshness filter or version-aware ranking boost...
```

That's real, unedited output. The `likely_cause` label and the confidence score are
computed, not an LLM guessing a number — but notice `causal_proximity` landed at its
0.3 floor here: in this trace the `retrieval` and `llm` spans are siblings (both
children of the same parent) rather than parent→child, so today's simple
graph-hop heuristic can't credit "retrieval feeds into the final answer" and falls
back to its off-path default. That's an honest current limitation of the heuristic,
not a hidden bug — see `docs/architecture.md` section 6.

Only 2 of the 4 confidence components show up above because this particular trace
had no prior execution to compare against. When one exists, `temporal_correlation`
and `historical_frequency` are real too — see the baseline example below. What's
**not** real yet, anywhere: a multi-hop "failure chain"
(`stale_document → incorrect_context → incorrect_output`) — see `ROADMAP_HONEST.md`.

### Historical baselines

If a prior successful execution of the same named trace exists, PyAgentHound diffs
model/prompt/retriever/tools/latency/tokens/execution-path against it — never
claiming causality, only stating what changed:

```
$ pyagenthound analyze <trace_id>
customer-support-request  (...)
status: ERROR   findings: 1
baseline: <baseline_trace_id> (most recent prior successful execution)

Findings

MEDIUM  Model changed since the last successful execution
  model was 'gpt-4o' in the most recent successful execution (...) and is
  'gpt-4-turbo' now. This is an observed change, not a claim that it caused
  the current outcome.
  confidence: 1.00
  recommendation: Investigate whether the model change contributed to the current result.

Root Cause Analysis (deterministic estimate, not verified truth)

Likely cause: Model changed since the last successful execution
  confidence: 0.87  (evidence_strength=1.00, causal_proximity=0.50, temporal_correlation=1.00)
  recommendation: Investigate whether the model change contributed to the current result.
```

Also real, unedited. `temporal_correlation=1.00` here is genuine: baseline-comparison
findings are, by construction, about a change between temporally adjacent
executions. `causal_proximity=0.50` reflects that a baseline finding is anchored to
the whole trace, one `PARENT`-edge hop from the single `llm` span in this minimal
example — a busier trace with more structure between the trace root and the final
span would score lower. `historical_frequency` only appears once there are multiple
prior executions to check the pattern's recurrence against.

### Replay

PyAgentHound doesn't own your agent's code, so it can't literally "call the LLM
again." What it can do: clone the trace, override a span's recorded attributes with
what a fix *would* have produced, and check whether the finding clears. Fixing the
stale-retrieval scenario above by overriding the retrieval span to return only the
current policy:

```
$ pyagenthound replay <trace_id> --set 'retrieval.documents=[{"id": "policy-2026", "date": "2026-01-01"}]'
Replayed <trace_id> -> <replayed_trace_id>
original findings: 1   replayed findings: 0
resolved: stale_retrieval_documents

inspect the replayed trace with:
  pyagenthound inspect <replayed_trace_id>
```

Real, unedited — the finding really does go to zero. Overriding a `TOOL`/`MCP` span
(or any span not explicitly annotated `safety=READ_ONLY`) is refused unless you pass
`--allow-unsafe`:

```
$ pyagenthound replay <trace_id> --set 'charge_card.amount=999'
Error: Replay would override non-READ_ONLY span(s) ['charge_card'] — pass
allow_unsafe=True to confirm. (pass --allow-unsafe to confirm)
```

### Evaluation / regression testing

A test case is a small, hand-authored JSON file asserting properties that should
hold for an already-captured trace — meant to be committed and run in CI:

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

```
$ pyagenthound test ./tests
PASS  cancellation_policy_mentions_window

all passed
```

Real output — and pointing that same test case at a genuinely regressed trace (the
stale documents came back) correctly flips it, with the specific broken assertion
named and a non-zero exit code for CI:

```
$ pyagenthound test ./tests
FAIL  cancellation_policy_mentions_window
  x NO_FINDING('stale_retrieval_documents'): 1 finding(s) matched
  'stale_retrieval_documents'

some failed
```

## What works today (Phase 1-7)

- A Python SDK (`pyagenthound`) with an OpenTelemetry-compatible tracing model:
  traces, spans (with AI-specific `SpanType`s — `LLM`, `RETRIEVAL`, `TOOL`, `MCP`,
  etc.), events, attributes, input/output, error capture.
- Local-first capture: no server required — traces write straight to a local SQLite
  database.
- An optional local API server (`pyagenthound serve`) + REST ingestion, if you want
  to centralize traces from multiple processes.
- A queryable execution graph (`GET /api/traces/{id}/graph`) built from each trace —
  spans linked by their parent/child structure, plus retrieved documents as their own
  nodes for basic data lineage.
- A deterministic rule engine (`POST /api/traces/{id}/analyze`, `pyagenthound
  analyze`) — 5 built-in rules covering retrieval, tool, and configuration failures,
  each returning evidence-backed findings, no LLM involved.
- Root-cause ranking (`GET /api/traces/{id}/root-cause`, also folded into
  `pyagenthound analyze`'s output) — turns findings into `likely_cause` /
  `contributing_factor` hypotheses with a confidence built from real, exposed
  components (see above).
- Historical baseline comparison — diffs a trace against the most recent prior
  successful execution of the same named workflow (model/prompt/retriever/tools/
  latency/tokens/execution path), and computes how often a given anomaly recurs
  across recent executions. Never claims causality, only states what changed.
- Replay (`POST /api/traces/{id}/replay`, `pyagenthound replay`) — clone a trace,
  override span attributes, and see whether a finding clears. Never re-invokes a
  live model/tool; a `READ_ONLY`/`WRITE`/`DESTRUCTIVE`/`UNKNOWN` safety
  classification refuses to override a non-`READ_ONLY` span without `--allow-unsafe`.
- Evaluation / regression testing (`pyagenthound test <tests_dir>`) — file-based
  JSON test cases asserting properties of a captured trace (status, output content,
  absence of a finding, spans present, tools not called), CI-gateable via a
  non-zero exit on failure.
- A CLI to inspect, analyze, replay, and test what was captured.

## Quickstart

```bash
pip install -e ".[dev]"     # until published to PyPI
pyagenthound init
```

```python
from pyagenthound import AgentHound, SpanType

hound = AgentHound()  # local-only, writes to ~/.pyagenthound/pyagenthound.db

with hound.trace("customer-support-request") as trace:
    with trace.span("retrieval", span_type=SpanType.RETRIEVAL) as span:
        span.set_attribute("query", "cancellation policy")
        span.set_attribute("documents", ["policy-2024", "policy-2026"])

    with trace.span("llm", span_type=SpanType.LLM) as span:
        span.set_attribute("model", "gpt-4o")
        span.set_output("You can cancel within 30 days...")
```

```bash
pyagenthound inspect <trace_id>
pyagenthound analyze <trace_id>
pyagenthound replay <trace_id> --set 'retrieval.documents=[]'   # try a fix
```

Full walkthrough, including the API server, in [`docs/quickstart.md`](docs/quickstart.md).

## vs Langfuse

Langfuse is the leading OSS LLM/agent observability platform and the
closest real comparison. **Methodology, stated plainly:** PyAgentHound was
live-tested end to end against a real agent making real calls to a local
Ollama model (`qwen2.5:7b-instruct`, zero cloud cost) with two real
failure scenarios built deliberately, not synthetic placeholders. Standing
up Langfuse's own multi-service stack (Postgres + ClickHouse + Redis +
web/worker containers) was judged too heavyweight for this pass, so the
Langfuse side of this comparison is feature-level, from its own public
docs — clearly marked below, not blended with the live-tested numbers.

**Scenario 1 (live-tested):** a tool returns technically-valid-but-incomplete
data (a real order lookup missing its `status` field); the downstream LLM
correctly says it doesn't have enough information rather than hallucinating.
No exception anywhere — `pyagenthound analyze` correctly reports **0
findings**, which is honest, not a miss: none of its rules claim to detect
"technically valid but semantically incomplete" tool output, and it says so
plainly rather than fabricating a finding.

**Scenario 2 (live-tested):** a tool genuinely crashes (a real
`json.JSONDecodeError` from malformed upstream data). `pyagenthound analyze`
correctly surfaced it:

```
HIGH  Tool call failed: tool.fetch_inventory
  Expecting value: line 1 column 32 (char 31)
  confidence: 1.00  (evidence_strength=1.00, causal_proximity=1.00, historical_frequency=1.00)
```

| | PyAgentHound (live-tested) | Langfuse (from public docs) |
|---|---|---|
| Deployment | Local-only, `pip install`, SQLite | Self-hosted (Postgres+ClickHouse+Redis+web/worker) or managed cloud |
| Tracing | Real spans, real attributes, real errors — verified above | Real, mature, widely-adopted OTel-based tracing |
| Root-cause ranking | Real deterministic rules + a decomposed confidence model (evidence/proximity/frequency) — verified finding a genuine crash | Not its focus — Langfuse surfaces traces/metrics/evals for a human (or your own downstream logic) to interpret; it doesn't ship an automated root-cause ranking engine |
| Counterfactual replay (`replay --set ...`) | Real — override a captured attribute and re-run to test a fix | Not a Langfuse feature |
| UI | CLI/API only as of this pass (a web UI is in progress, untracked in this repo as of this benchmark) | Mature, full-featured web UI |
| Scale/maturity | Early-stage, single-machine | Production-proven at real scale, large user base |

**Bug found and fixed while running this benchmark:** a span's error status
never propagated to its parent trace's status when the caller caught the
exception itself (a normal pattern — retry/graceful-degradation code, not
an edge case). `trace.status` stayed `OK` even when `analyze` correctly
found a real `HIGH` tool failure inside it, which would silently break any
status-based trace filtering ("show me failed traces"). Fixed in
`pyagenthound/sdk/client.py`'s `SpanContext.record_error`; regression test
added (`tests/unit/test_sdk_client.py`); 109/109 tests pass.

**Bottom line:** Langfuse is the mature, production-proven choice for
tracing infrastructure and scale. PyAgentHound's real differentiator,
verified live here, is going a step further than tracing — a working,
non-trivial root-cause ranking engine and counterfactual replay — but it's
early-stage, CLI-only, and single-machine as of this pass.

## Where this is going

The core pipeline this project is building toward:

```
Trace → Graph → Evidence → Findings → Causal hypotheses → Replay → Evaluation
```

Execution graph with typed relationships and data lineage (built), deterministic
rule engine (built — 5 rules; LLM-powered analysis is optional and additive, never
required), root-cause ranking with an explicit, fully-implemented confidence model
(built), historical baseline comparison (built), safe replay with a
read/write/destructive safety classification (built), and a regression test suite
you can run in CI (built). See [`docs/architecture.md`](docs/architecture.md) for
the full design and [`ROADMAP_HONEST.md`](ROADMAP_HONEST.md) for what's actually
shipped vs. planned at any point in time.

Still missing: a web UI (everything above is CLI/API-only today) and any
LLM-powered analysis layer (deterministic rules stay the default and requirement;
LLM analysis would only ever be additive, per the design principles below).

## Design principles

1. Evidence first — every finding references evidence, no opaque "AI says this is wrong."
2. Deterministic analysis wherever possible; AI reasoning only where it adds value, and always optional.
3. Provider-neutral, local-first, runs entirely on your machine with no cloud dependency.
4. Python is the primary developer API. Rust is used only where profiling justifies it — not by default.

## License

Apache-2.0 — see [`LICENSE`](LICENSE).
