# Audit findings — 2026-10-19

This file records the repository-specific findings from the portfolio audit
conducted on 2026-10-19. It is documentation only; no code or release artifacts
were changed in this pass unless explicitly noted under "Implementation status".

Sources: the repository's own README/source/workflows, GitHub metadata and
Actions runs, PyPI metadata, and official competitor documentation. Claims are
marked as verified, inferred, or open questions. "Absent" means not found in the
inspected repository/docs, not proof that it cannot exist.

## What it is

Trace and root-cause AI agent/LLM application failures: OTel-compatible traces, local SQLite, deterministic rules, replay, evaluation, and a web UI.

## Verified strengths

- OTel-compatible trace/span model with AI span types; local-first SQLite; optional API server; execution graph; 5 deterministic rules; confidence decomposition; baseline diff; safe replay with read/write classification; JSON eval cases; 19 tests.
- Root-cause explanation is the differentiator, not another tracing UI.

## Verified gaps and user-facing risks

- Not on PyPI; explanation layer is local Ollama only; no multi-hop failure chains; replay never re-invokes tools/models; pre-alpha.
- No production scale or accuracy evaluation; no GitHub release.

## Direct competitors

- Langfuse, Arize Phoenix, AgentOps, Braintrust, LangSmith.

## Ranked next actions

- P1: publish PyPI + OTel ingestion + cloud LLM explanations (M).
- P2: multi-hop causal chains (L).

## Do not build

- A hosted observability UI; integrate with OTel/Langfuse/Phoenix.

## Evidence gaps / validation needed

- No real agent traces; no precision/recall evaluation of rules or confidence.

## Recommended disposition

Invest narrowly as a diagnosis layer; do not compete on tracing infrastructure.

## Implementation status

No code changes in this pass.
