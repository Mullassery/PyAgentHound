# PyAgentHound

Evidence-based debugging and root-cause analysis for AI agents and LLM applications — trace, analyze, replay, and explain why a run produced its result.

[![CI](https://github.com/Mullassery/PyAgentHound/actions/workflows/ci.yml/badge.svg)](https://github.com/Mullassery/PyAgentHound/actions/workflows/ci.yml)
[![Python 3.10+](https://img.shields.io/badge/Python-3.10%2B-blue)](https://www.python.org)
[![License: Apache 2.0](https://img.shields.io/badge/License-Apache%202.0-blue.svg)](LICENSE)
[![PyPI](https://img.shields.io/pypi/v/pyagenthound.svg)](https://pypi.org/project/pyagenthound/)

> **Status: Phase 1–9 MVP (Pre-Alpha).** Trace capture, storage, inspection, a
> queryable execution graph, a deterministic rule engine (5 built-in rules),
> root-cause ranking, historical baseline comparison, safe replay, file-based
> evaluation/regression testing, a server-rendered web UI, and an optional
> LLM-powered explanation layer (local Ollama, evidence-grounded) work end to end
> and are tested — see [ROADMAP_HONEST.md](ROADMAP_HONEST.md) for the exact
> built-vs-not line.

> **Not to be confused with [PyVectorHound](https://github.com/Mullassery/PyVectorHound):** PyAgentHound traces and root-causes AI *agent* failures; PyVectorHound diagnoses *RAG retrieval* failures.

## Which project do I need?

Part of the Mullassery open-source family. These tools have similar names — here is the short version of who does what:

| If you need to… | Use |
| --- | --- |
| Build a repository's dependency graph and match it against vulnerability advisories (Python, Rust, Node, containers) | [PyDeepMesh](https://github.com/Mullassery/PyDeepMesh) |
| Understand *why* a Python dependency exists, who added it, and whether it is actually used | [PyDependencyCheck](https://github.com/Mullassery/PyDependencyCheck) |
| Statically analyze a **dbt** project (risky tests, test blast radius, cost) | [PyDBTGuard](https://github.com/Mullassery/PyDBTGuard) |
| Statically analyze **Apache Beam / Dataflow** pipelines (cost, hot keys, reliability) | [PyBeamGuard](https://github.com/Mullassery/PyBeamGuard) |
| Validate **Airflow** DAGs and dbt runs | [PyAirflowTester](https://github.com/Mullassery/PyAirflowTester) |
| Simulate cascading-failure **blast radius** across infrastructure, data pipelines, and AI systems | [PyBlastRadius](https://github.com/Mullassery/PyBlastRadius) |
| Check the **quality of the data itself** at runtime (schema, drift, anomalies) | [StatGuardian](https://github.com/Mullassery/StatGuardian) |
| Discover **devices, services, and vulnerabilities on a network** | [PyNetworkIntel](https://github.com/Mullassery/PyNetworkIntel) |
| Discover and score **API security** risk (real traffic, agent/MCP, Cedar policy) | [PyAPICheck](https://github.com/Mullassery/PyAPICheck) |
| Trace and root-cause **AI agent** failures | [PyAgentHound](https://github.com/Mullassery/PyAgentHound) |
| Diagnose **RAG retrieval** failures | [PyVectorHound](https://github.com/Mullassery/PyVectorHound) |
| Orchestrate **local, dependency-aware tasks** (DAG scheduler + content-addressed cache) | [PyTaskWireCheck](https://github.com/Mullassery/PyTaskWireCheck) |

[Browse all projects →](https://github.com/Mullassery?tab=repositories)

## What it is

PyAgentHound answers a specific question conventional observability does not:

> **Why did my AI application produce this result?**

not just "what happened during this request?" It captures execution evidence
across the full path (request → agent → prompt → retriever → vector DB →
tools/MCP → model → response), assembles it into a causal execution graph, and
runs deterministic analysis over that graph. Every finding distinguishes
**observed facts** from **detected anomalies** from **inferred causes** from
**recommendations**, and every conclusion carries an evidence reference — an
inference is never presented as a fact.

It is local-first: traces write straight to a local SQLite database, and an
optional local Ollama model can narrate findings. No cloud dependency.

## Features / Highlights

- **OpenTelemetry-compatible tracing model** — traces, spans with AI-specific
  `SpanType`s (`LLM`, `RETRIEVAL`, `TOOL`, `MCP`, ...), events, attributes,
  input/output, and error capture, via the `pyagenthound` Python SDK.
- **Local-first capture** — no server required; traces write to a local SQLite
  database. An optional API server (`pyagenthound serve`) + REST ingestion
  centralizes traces from multiple processes.
- **Queryable execution graph** — spans linked by parent/child structure, plus
  retrieved documents as their own nodes for basic data lineage.
- **Deterministic rule engine** — 5 built-in rules covering retrieval, tool, and
  configuration failures; each returns evidence-backed findings, with no LLM
  involved.
- **Root-cause ranking** — turns findings into `likely_cause` /
  `contributing_factor` hypotheses with a confidence score decomposed into
  visible components (evidence strength, causal proximity, temporal
  correlation, historical frequency).
- **Historical baseline comparison** — diffs a trace against the most recent
  prior successful execution of the same named workflow; never claims causality,
  only states what changed.
- **Safe replay** — clone a trace, override span attributes, and check whether a
  finding clears; a `READ_ONLY`/`WRITE`/`DESTRUCTIVE`/`UNKNOWN` safety
  classification refuses to override a non-`READ_ONLY` span without
  `--allow-unsafe`.
- **Evaluation / regression testing** — file-based JSON test cases asserting
  properties of a captured trace, CI-gateable via a non-zero exit on failure.
- **Web UI** — server-rendered (FastAPI + Jinja2, no npm/build step): requests
  list, request detail with an interactive execution graph, findings, root-cause
  hypotheses, and a replay form.
- **Optional LLM explanation** — a local Ollama model narrates existing findings
  in plain English; it never invents evidence, and any unsupported citation is a
  hard rejection.

## Who it's for / Use cases

- **Agent/LLM developers** debugging an AI-shaped failure — stale retrieval, the
  wrong tool selected, a silently changed prompt, truncated context.
- **Teams adding AI regression tests** that assert a captured trace still
  behaves (status, output content, absence of a finding, tools not called) in CI.
- **Anyone who needs a local, private, single-machine debugging loop** — the
  whole pipeline runs on your machine.
- **Practitioners who want to test a hypothesized fix** without re-invoking live
  models or tools, using replay.

## What it is not

- **Not a full observability platform.** It is early-stage, CLI/web-UI, and
  single-machine — not a replacement for a mature, widely-deployed tracing
  backend at scale.
- **Not cloud-provider supported for explanations.** The explanation layer is
  local Ollama only; cloud providers (OpenAI, Anthropic, etc.) are deliberately
  not built rather than built-and-unverified. `LLMProvider` is a small Protocol.
- **No multi-hop failure chains yet.** A chain like
  `stale_document → incorrect_context → incorrect_output` is not implemented.
- **Not a live re-runner.** Replay clones a captured trace and overrides
  attributes; it never re-invokes a real model or tool.
- **Not yet production-hardened.** Pre-Alpha: expect rough edges and evolving
  interfaces.

## Project status

**Pre-Alpha (v0.1.0).** Phases 1–9 are implemented and tested end to end. What's
still missing (cloud LLM providers for the explanation layer, multi-hop failure
chains) is documented rather than stubbed. See
[ROADMAP_HONEST.md](ROADMAP_HONEST.md) for the current built-vs-planned line and
[docs/architecture.md](docs/architecture.md) for the full design.

## Inspect AI evaluation interop

Turn recorded traces into Inspect AI samples and run an Inspect task:

```bash
pip install "pyagenthound[inspect]"
```

```python
from pyagenthound import traces_to_dataset

samples = traces_to_dataset(store.list_traces())  # ids/input/target/metadata
```

`trace_to_sample()` uses span inputs and the last span output as the target,
with trace id/status/tags as metadata. `evaluate_with_inspect(traces, task,
model=...)` runs Inspect's `eval()` over the converted dataset. No target is
fabricated: traces without outputs produce an empty target.

## OpenTelemetry / OpenInference ingestion

Point an existing OTLP exporter at PyAgentHound instead of rewriting your
instrumentation:

```bash
# JSON (no extra dependency)
OTEL_EXPORTER_OTLP_TRACES_ENDPOINT=http://localhost:8787/v1/traces \
OTEL_EXPORTER_OTLP_TRACES_PROTOCOL=http/json your-agent

# Protobuf (install the optional proto package)
pip install "pyagenthound[otlp]"
```

`POST /v1/traces` accepts OTLP/HTTP JSON and protobuf, groups spans by
`traceId`, and maps OpenInference/GenAI span kinds (`LLM`, `TOOL`,
`RETRIEVER`, `EMBEDDING`, `RERANKER`, `AGENT`) plus attributes such as
`gen_ai.request.model`, `input.value` and `output.value` into PyAgentHound's
native model. Run `pyagenthound serve` and open the dashboard as usual.

## Installation

Python 3.10+:

```bash
pip install pyagenthound
pyagenthound init
```

For development, clone and install the editable development dependencies:

```bash
git clone https://github.com/Mullassery/PyAgentHound.git
cd PyAgentHound
pip install -e ".[dev]"
```

## Quick start

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
pyagenthound analyze <trace_id> --explain   # optional: local-LLM narrative (needs Ollama)
pyagenthound serve   # then open http://localhost:8787 for the web UI
```

## Usage

CLI commands:

| Command | Purpose |
|---|---|
| `pyagenthound init` | Initialize local storage/config. |
| `pyagenthound inspect <trace_id>` | Inspect a captured trace. |
| `pyagenthound analyze <trace_id>` | Run the rule engine; add `--explain` for the optional local-LLM narrative. |
| `pyagenthound replay <trace_id> --set '<attr>=<value>'` | Clone and override a span; refuses non-`READ_ONLY` spans unless `--allow-unsafe`. |
| `pyagenthound test <tests_dir>` | Run file-based JSON evaluation/regression cases (non-zero exit on failure). |
| `pyagenthound serve` | Start the API server and web UI (`http://localhost:8787`). |

Evaluation test case example:

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

```bash
pyagenthound test ./tests
```

## Documentation

- [docs/quickstart.md](docs/quickstart.md) — full walkthrough, including the API
  server.
- [docs/architecture.md](docs/architecture.md) — execution graph, evidence
  model, and the root-cause confidence design.
- [ROADMAP_HONEST.md](ROADMAP_HONEST.md) — what's shipped vs. planned, with the
  honest limitations spelled out.
- [CHANGELOG.md](CHANGELOG.md) — release history.
- [CONTRIBUTING.md](CONTRIBUTING.md) — contribution guidelines.
- [SECURITY.md](SECURITY.md) — how to report a vulnerability.

## Known issues and deferred work

**Blocked / failed:**
- PyPI publication, OTel ingestion, cloud LLM explanations, multi-hop chains.

**Rejected / deferred:**
- Hosted observability UI; integrate with OTel/Langfuse/Phoenix.

Full shipped/blocked/rejected detail: [`QUEUE_STATUS.md`](QUEUE_STATUS.md).

## Contributing

Contributions are welcome — see [CONTRIBUTING.md](CONTRIBUTING.md). Run the same
checks CI runs:

```bash
pip install -e ".[dev]"
ruff check pyagenthound tests examples
mypy pyagenthound
pytest -q
```

## License

Apache-2.0 — see [LICENSE](LICENSE).
