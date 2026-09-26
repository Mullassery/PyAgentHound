# Changelog

All notable changes to this project are documented in this file.

## [Unreleased]

### Added
- Phase 6: replay (`pyagenthound/replay/`) — `classify_span_safety()`
  (READ_ONLY/WRITE/DESTRUCTIVE/UNKNOWN, conservative defaults), `build_plan()`,
  `apply_overrides()` (clones a trace with fresh ids + per-span attribute
  overrides — a counterfactual edit, never a re-invocation of the agent),
  `run_replay()` (safety-gated; re-runs the rule engine on both traces and returns
  the finding diff). `POST /api/traces/{id}/replay` (`409` on an unconfirmed unsafe
  override) and `pyagenthound replay <id> --set NAME.KEY=VALUE [--allow-unsafe]`.
- Phase 5: historical baselines (`pyagenthound/baseline/`) — `ExecutionSignature`/
  `extract_signature()`, `find_baseline()` (most recent prior `status=OK` execution
  of the same named workflow), `compare_to_baseline()` (model/prompt/retriever/
  tools/execution-path/latency/token-usage changes as `Finding`s, each an observed
  change, never a causal claim), `historical_rule_frequencies()`. Completes the
  root-cause confidence model — `temporal_correlation` and `historical_frequency`
  are now real, computed values (previously always `None`). `list_traces` (storage +
  API) gained a `name` filter to support this. Wired into `POST .../analyze`,
  `GET .../root-cause`, and `pyagenthound analyze`.
- Phase 4: root-cause engine (`pyagenthound/rootcause/`) — `ConfidenceComponents`/
  `RootCauseHypothesis` domain model, `rank_root_causes()`. Turns findings into
  ranked `likely_cause`/`contributing_factor` hypotheses using two real confidence
  components (`evidence_strength`, `causal_proximity`); `temporal_correlation` and
  `historical_frequency` stay `None` pending historical baseline storage (not
  built). Exposed via `GET /api/traces/{id}/root-cause` and folded into
  `pyagenthound analyze`'s output.
- Phase 3: deterministic rule engine (`pyagenthound/rules/`) — `Finding`/`Evidence`/
  `FailureCategory`/`Severity` domain model, `Rule` protocol, `run_rules()`, and 5
  built-in rules (`empty_retrieval`, `stale_retrieval_documents`,
  `duplicate_retrieved_documents`, `tool_failure`, `dangling_parent_span`). Exposed
  via `POST /api/traces/{id}/analyze` and `pyagenthound analyze <id>`.
- Phase 2: execution graph (`pyagenthound/graph/`) — `Node`/`Edge`/`ExecutionGraph`
  domain model with query methods (by type, by relationship, by time window,
  neighbors, ancestors), `build_graph()` construction from a trace, a `RETRIEVAL`
  → `DOCUMENT` attribute extractor, and `GET /api/traces/{id}/graph`.
- Phase 1: tracing model (`Trace`/`Span`/`Event`/`SpanType`/`SpanStatus`), SDK
  (`AgentHound`, context managers + decorators), SQLite storage (`SQLiteTraceStore`),
  local-first + HTTP export, FastAPI ingestion/query API, CLI (`init`, `serve`,
  `inspect`).
