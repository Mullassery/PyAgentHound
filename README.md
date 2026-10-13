# PyAgentHound

Evidence-based debugging and root-cause analysis for AI agents and LLM applications — trace, analyze, replay, and explain why a run produced its result.

[![CI](https://github.com/Mullassery/PyAgentHound/actions/workflows/ci.yml/badge.svg)](https://github.com/Mullassery/PyAgentHound/actions/workflows/ci.yml)
[![Python 3.10+](https://img.shields.io/badge/Python-3.10%2B-blue)](https://www.python.org)
[![License: Apache 2.0](https://img.shields.io/badge/License-Apache%202.0-blue.svg)](LICENSE)

> **Status: Phase 1–9 MVP (Pre-Alpha).** Trace capture, storage, inspection, a
> queryable execution graph, a deterministic rule engine (5 built-in rules),
> root-cause ranking, historical baseline comparison, safe replay, file-based
> evaluation/regression testing, a server-rendered web UI, and an optional
> LLM-powered explanation layer (local Ollama, evidence-grounded) work end to end
> and are tested — see [ROADMAP_HONEST.md](ROADMAP_HONEST.md) for the exact
> built-vs-not line.

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
- **Not published to PyPI.** Install from source for now.
- **Not yet production-hardened.** Pre-Alpha: expect rough edges and evolving
  interfaces.

## Project status

**Pre-Alpha (v0.1.0).** Phases 1–9 are implemented and tested end to end. What's
still missing (cloud LLM providers for the explanation layer, multi-hop failure
chains) is documented rather than stubbed. See
[ROADMAP_HONEST.md](ROADMAP_HONEST.md) for the current built-vs-planned line and
[docs/architecture.md](docs/architecture.md) for the full design.

## Installation

Not yet published to PyPI — install from source (Python 3.10+):

```bash
git clone https://github.com/Mullassery/PyAgentHound.git
cd PyAgentHound
pip install -e ".[dev]"     # until published to PyPI
pyagenthound init
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

## Contributing

Contributions are welcome — see [CONTRIBUTING.md](CONTRIBUTING.md). Run the same
checks CI runs:

```bash
pip install -e ".[dev]"
ruff check pyagenthound tests examples
mypy pyagenthound
pytest -q
```

## Related projects

- [PyAPICheck](https://github.com/Mullassery/PyAPICheck) — API security discovery with cited risk scores
- [PyBeamGuard](https://github.com/Mullassery/PyBeamGuard) — Apache Beam and Dataflow pipeline analysis
- [PyNetworkIntel](https://github.com/Mullassery/PyNetworkIntel) — network discovery and anomaly detection
- [OpenAnchor](https://github.com/Mullassery/OpenAnchor) — LLM token-usage intelligence middleware
- [PyAgentHound](https://github.com/Mullassery/PyAgentHound) — trace, detect, and explain AI agent failures
- [PyVectorHound](https://github.com/Mullassery/PyVectorHound) — diagnose RAG retrieval failures
- [Browse all projects](https://github.com/Mullassery?tab=repositories)

## License

Apache-2.0 — see [LICENSE](LICENSE).
