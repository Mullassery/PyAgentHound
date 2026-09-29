# Changelog

All notable changes to this project are documented in this file.

## [Unreleased]

### Added
- Phase 9: optional LLM-powered explanation (`pyagenthound/llm/`) — `LLMProvider`
  Protocol, `OllamaProvider` (local, no API key). `explain_root_cause()` shows a
  model only the structured findings/hypotheses already computed and requires
  strict JSON output; any cited `finding_id` not present in the real findings is a
  hard `LLMOutputValidationError`. `pyagenthound analyze --explain` and
  `POST /api/traces/{id}/explain` (`400`/`503`/`422`); both fail soft rather than
  crash when no LLM is running. Verified against a real local `qwen2.5:7b-instruct`.

### Fixed
- `Finding.finding_id` was a random UUID generated fresh on every construction;
  since findings are recomputed from scratch on every `analyze`/`root-cause`/
  `explain` call rather than persisted, two separate `run_rules()` calls over the
  identical trace produced different ids for the same logical finding. Now a
  deterministic hash of `rule_id` + `affected_nodes`.

### Added
- Phase 8: web UI (`pyagenthound/ui/`) — server-rendered (FastAPI + Jinja2, no
  npm/build step). `GET /` (requests list, `name`/`status` filters),
  `GET /requests/{id}` (consolidated detail: metadata, interactive execution graph,
  timeline, findings, root-cause hypotheses, replay form), `POST
  /requests/{id}/replay` (redirects to the replayed trace on success, or back with
  `?replay_error=` on an unconfirmed unsafe override). The graph is vanilla JS
  fetching the existing `GET /api/traces/{id}/graph` JSON — no graphing library.
  7 integration tests plus a real browser walkthrough verifying the full
  fix-and-replay loop end to end.
- Phase 7: evaluation / regression testing (`pyagenthound/evaluation/`) —
  `TestCase`/`Assertion`/`AssertionResult`/`TestCaseResult` domain model, `evaluate()`
  with 5 assertion types (`STATUS_OK`, `OUTPUT_CONTAINS`, `NO_FINDING` — checked
  against the real rule engine, `SPAN_EXISTS`, `NO_TOOL_CALLED`), JSON file I/O.
  `pyagenthound test <tests_dir>` runs every `*.json` test case, PASS/FAIL per case,
  non-zero exit on failure for CI. No API endpoint by design — test cases are
  file-based, meant for version control.
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
