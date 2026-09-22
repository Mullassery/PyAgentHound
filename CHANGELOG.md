# Changelog

All notable changes to this project are documented in this file.

## [Unreleased]

### Added
- Phase 2: execution graph (`pyagenthound/graph/`) — `Node`/`Edge`/`ExecutionGraph`
  domain model with query methods (by type, by relationship, by time window,
  neighbors, ancestors), `build_graph()` construction from a trace, a `RETRIEVAL`
  → `DOCUMENT` attribute extractor, and `GET /api/traces/{id}/graph`.
- Phase 1: tracing model (`Trace`/`Span`/`Event`/`SpanType`/`SpanStatus`), SDK
  (`AgentHound`, context managers + decorators), SQLite storage (`SQLiteTraceStore`),
  local-first + HTTP export, FastAPI ingestion/query API, CLI (`init`, `serve`,
  `inspect`).
