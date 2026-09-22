# PyAgentHound

**Evidence-based debugging and root-cause analysis for AI agents and LLM applications.**

> **Status: Phase 1-3 MVP.** Trace capture, storage, inspection, a queryable execution
> graph, and a deterministic rule engine (5 built-in rules) work end to end and are
> tested. The root-cause engine, web UI, replay, and evaluation described below in
> "Where this is going" are **not built yet** — see
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

## How it will find root causes (design target, not yet built)

```
❌ Agent returned incorrect customer status

Root cause:
    Stale retrieval context

Evidence:
    3 retrieved documents were older than the active policy version.

Failure chain:
    stale_document → incorrect_context → incorrect_model_output

Confidence: 94%
```

Every finding distinguishes **observed facts** from **detected anomalies** from
**inferred causes** from **recommendations** — an inference is never presented as a
fact, and every conclusion carries an evidence reference. See
[`docs/architecture.md`](docs/architecture.md) for the full design, including how
confidence scores are built from deterministic components rather than an LLM
guessing a number.

What's real today is the "detected anomalies" layer, not yet the "inferred causes" or
"failure chain" layer above — `pyagenthound analyze <trace_id>` runs 5 deterministic
rules (including the stale-document one) and prints findings with their evidence, but
there's no root-cause ranking or confidence-scored explanation yet.

## What works today (Phase 1-3)

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

Deterministic rule engine (built — 5 rules; LLM-powered analysis is optional and
additive, never required), execution graph with typed relationships and data lineage
(built), a root-cause engine with an explicit, decomposed confidence model,
historical baseline comparison,
safe replay with a read/write/destructive safety classification, and a regression
test suite you can run in CI. See [`docs/architecture.md`](docs/architecture.md) for
the full design and [`ROADMAP_HONEST.md`](ROADMAP_HONEST.md) for what's actually
shipped vs. planned at any point in time.

## Design principles

1. Evidence first — every finding references evidence, no opaque "AI says this is wrong."
2. Deterministic analysis wherever possible; AI reasoning only where it adds value, and always optional.
3. Provider-neutral, local-first, runs entirely on your machine with no cloud dependency.
4. Python is the primary developer API. Rust is used only where profiling justifies it — not by default.

## License

Apache-2.0 — see [`LICENSE`](LICENSE).
