# Competitive intelligence in roadmap and upgrade work

**Policy date:** 2026-10-19

Competitive findings are an input to product decisions, not a one-off report.
Every pending roadmap item, new feature, and routine dependency upgrade should
check the repository's [`AUDIT_FINDINGS.md`](AUDIT_FINDINGS.md) before work
starts, and record the decision in the PR or changelog.

## Required check before building

1. **Read `AUDIT_FINDINGS.md`.** Find the relevant competitor row and the
   ranked next actions. If the finding is stale, update it with a dated source.
2. **Name the competitor and the user problem.** A feature is not justified by
   "competitor has it". State the workflow it unlocks, who needs it, and how
   often. Mark unverified demand as a hypothesis.
3. **Prefer reuse over new code.** Check whether an existing Mullassery repo
   already provides the capability (see `BUNDLES.md` in the profile repo and
   the bundle role file in this repo, when present). Typical reuse:
   - crawling/fetching/robots/SSRF → **MudFish**
   - architecture maps / PR diffs → **CodeAtlas**
   - data-quality contracts / validation → **StatGuardian**
   - token counting / cost tables → **PyTokenCalc**
   - dependency graph / advisories / SBOM → **PyDeepMesh**
   - segmentation / CLV / churn → **ClusterAudienceKit**
   - activation / lineage / PII → **PyReverseETL**
   - fleet state sync → **SyncFleet** (only after conflict resolution)
4. **Choose one disposition:** build, integrate, defer, or reject. Write it
   down. A rejection with a reason is a successful outcome.
5. **For routine upgrades**, check whether the upgrade closes a known
   competitor gap or breaks a differentiated capability. Run the tests that
   cover the affected path; do not merge a green build that silently changes a
   user-visible contract.

## PR / changelog checklist

- [ ] Competitor and source URL/date recorded (or "no direct competitor").
- [ ] User impact and frequency stated; unverified demand labelled.
- [ ] Reuse check done against sibling repos/bundles.
- [ ] Failure mode and rollback considered (especially auth, PII, cost).
- [ ] Docs/roadmap status updated honestly.
- [ ] Tests or a manual verification command included.

## Review cadence

- Refresh the competitor row when a release changes the capability.
- Re-check the full `AUDIT_FINDINGS.md` at least quarterly and before a major
  release.
- If a finding is wrong or stale, correct it in the same PR that relies on it.

## Non-goals

- Copying features for parity.
- Adding a dependency just because a competitor uses it.
- Treating star counts or download counts as proof of user need.

## OSS gap analysis — 2026-10-24

**Scope.** Covers PyAgentHound v0.2.0 as implemented here: trace storage,
execution-graph queries, five deterministic rules, root-cause ranking, baseline
comparison, attribute-override replay, file-based evaluation, the UI, and local
Ollama explanations. Hosted SaaS is excluded unless its core is OSS.

### Comparable OSS projects

| Project | License | Activity | Why comparable |
|---|---|---|---|
| Langfuse | MIT (core) | SDK 5.0.4, 2026-10-21 | Traces, evals, prompts, and cost analytics for LLM apps |
| Arize Phoenix | ELv2 | 20.x; 20.23.0, 2026-10-16 | OSS tracing, evaluation, and experiments |
| AgentOps | MIT | 0.4.21, 2025-08-29; repo 2026-06-25 | Agent-focused tracing and session replay |
| OpenLLMetry | Apache-2.0 | 0.62.4, 2026-09-29 | Instrumentation that emits OpenTelemetry traces |

### Capability comparison

| Capability | PyAgentHound | Langfuse | Phoenix | AgentOps | OpenLLMetry |
|---|---|---|---|---|---|
| Trace storage | Yes | Yes | Yes | Yes | No |
| OTLP ingestion | Yes | Yes | Yes | Partial | No |
| Deterministic rule engine | Yes | No | No | No | No |
| Root-cause ranking | Yes | No | No | No | No |
| Historical baseline comparison | Yes | No | No | No | No |
| Replay of a captured run | Yes | No | No | Partial | No |
| Eval or regression suite | Yes | Yes | Yes | Partial | No |
| Server-rendered UI | Yes | Yes | Yes | Yes | No |
| Local-only operation | Yes | No | Partial | No | No |
| Cost tracking | No | Yes | Partial | Yes | Partial |
| Framework auto-instrumentation | Partial | Partial | Partial | Yes | Yes |

"Partial": OpenLLMetry emits but does not store spans; Langfuse/Phoenix rely on
separate instrumentors; AgentOps replay is observational and its OTLP support is
unverified; Phoenix can run one local node. PyAgentHound has no native instrumentors.

### Gaps that matter (ranked)

1. **Rule coverage is the core product gap.** Five rules cover only part of the
   specified failure categories. Users will hit failures that produce no finding,
   which looks like a clean run. Build fixtures and explicit "uncovered category"
   reporting before broadening the UI.

2. **No native framework or provider instrumentation.** Debugging starts only
   after wiring the SDK or shipping OTLP. Integrate OpenLLMetry/OpenInference
   instrumentors rather than writing per-framework adapters; make OTLP JSON,
   which already works, easy to discover.

3. **Replay overrides attributes; it does not re-run the agent.** It clones a
   trace, applies overrides, and checks whether a finding would clear. Safe, but
   it cannot validate a code or prompt change. A sandboxed re-execution harness
   would be differentiated only with explicit side-effect controls.

4. **Operational surface is single-user.** SQLite plus a server-rendered UI with
   no auth, RBAC, retention, alerting, or horizontal scale. Defer team features
   unless deployment demand is recorded; do not grow a hosted product by accident.

5. **Evaluation is deterministic only.** No semantic/LLM-judge evaluation,
   dataset management, or experiment comparison. Add an optional evidence-grounded
   judge, keeping rules as the default and never letting a judge invent findings.

### Where we are differentiated

- Root causes are evidence-based, ranked with inspectable confidence components,
  and reproducible without an LLM; the optional Ollama layer only explains.
- The workflow is integrated: trace, graph, rules, baseline, replay, and tests
  share one model, rather than being separate dashboard features.
- Local-first storage and local explanations fit privacy-sensitive agent work.
- Safe replay refuses non-read-only spans unless explicitly allowed.

### Disposition

- **Build:** more deterministic rules with fixtures and coverage reporting; a
  sandboxed re-execution replay; a CI regression command that is easy to wire.
- **Integrate/reuse:** OpenLLMetry/OpenInference instrumentation and OTLP;
  export to Langfuse or Phoenix for team dashboards and semantic evals;
  PyTokenCalc for token/cost rollups.
- **Defer/reject:** multi-tenant hosting, RBAC, broad dashboard parity, and
  LLM-judge-only analysis. Those are established products, not the wedge.

### Sources

- Langfuse: https://github.com/langfuse/langfuse (MIT core; PyPI 5.0.4, 2026-10-21).
- Phoenix: https://github.com/Arize-ai/phoenix (20.23.0, 2026-10-16; ELv2).
- AgentOps: https://github.com/AgentOps-AI/agentops (MIT; 0.4.21, 2025-08-29; repo 2026-06-25).
- OpenLLMetry: https://github.com/traceloop/openllmetry (0.62.4, 2026-09-29; Apache-2.0).
- Local: `README.md`, `docs/architecture.md`, `pyagenthound/rules/builtin.py`,
  `pyagenthound/rootcause/engine.py`, `pyagenthound/ingest/otlp.py`.
