# Changelog

All notable changes to this project are documented in this file.

## [Unreleased]

### Added
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
