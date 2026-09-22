# PyAgentHound

**Evidence-based debugging and root-cause analysis for AI agents and LLM applications.**

> **Status: Phase 1-4 MVP.** Trace capture, storage, inspection, a queryable execution
> graph, a deterministic rule engine (5 built-in rules), and root-cause ranking work
> end to end and are tested. Historical baselines, LLM-powered analysis, web UI,
> replay, and evaluation described below in "Where this is going" are **not built
> yet** — see [`ROADMAP_HONEST.md`](ROADMAP_HONEST.md) for the exact built-vs-not
> line.

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
  confidence: 0.75  (evidence_strength=0.95, causal_proximity=0.30)
  recommendation: Add a freshness filter or version-aware ranking boost...
```

That's real, unedited output. The `likely_cause` label and the confidence score are
computed, not an LLM guessing a number — but notice `causal_proximity` landed at its
0.3 floor here: in this trace the `retrieval` and `llm` spans are siblings (both
children of the same parent) rather than parent→child, so today's simple
graph-hop heuristic can't credit "retrieval feeds into the final answer" and falls
back to its off-path default. That's an honest current limitation of the heuristic,
not a hidden bug — see `docs/architecture.md` section 6. What's **not** real yet: a
multi-hop "failure chain" (`stale_document → incorrect_context → incorrect_output`)
and the `temporal_correlation`/`historical_frequency` confidence components, both of
which need historical baseline storage across multiple traces (not built — see
`ROADMAP_HONEST.md`).

## What works today (Phase 1-4)

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
- A CLI to inspect and analyze what was captured.

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
```

Full walkthrough, including the API server, in [`docs/quickstart.md`](docs/quickstart.md).

## Where this is going

The core pipeline this project is building toward:

```
Trace → Graph → Evidence → Findings → Causal hypotheses → Replay → Evaluation
```

Execution graph with typed relationships and data lineage (built), deterministic
rule engine (built — 5 rules; LLM-powered analysis is optional and additive, never
required), root-cause ranking with an explicit confidence model (built, partial —
2 of the model's components are live, 2 need historical baselines that don't exist
yet), historical baseline comparison, safe replay with a read/write/destructive
safety classification, and a regression test suite you can run in CI. See
[`docs/architecture.md`](docs/architecture.md) for the full design and
[`ROADMAP_HONEST.md`](ROADMAP_HONEST.md) for what's actually shipped vs. planned at
any point in time.

## Design principles

1. Evidence first — every finding references evidence, no opaque "AI says this is wrong."
2. Deterministic analysis wherever possible; AI reasoning only where it adds value, and always optional.
3. Provider-neutral, local-first, runs entirely on your machine with no cloud dependency.
4. Python is the primary developer API. Rust is used only where profiling justifies it — not by default.

## License

Apache-2.0 — see [`LICENSE`](LICENSE).
