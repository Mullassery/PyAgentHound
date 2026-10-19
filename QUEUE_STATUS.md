# Queue status — 2026-10-19

This file records what was shipped, what is blocked/failed, and what is rejected for this repository. It complements `AUDIT_FINDINGS.md`.

## Shipped
- OTLP/OpenInference trace ingestion (`POST /v1/traces`, JSON + optional protobuf) and Inspect AI interop (0.2.0).

## Blocked / failed
- PyPI publication, cloud LLM explanations, multi-hop chains.

## Rejected / deferred
- Hosted observability UI; integrate with OTel/Langfuse/Phoenix.

## Policy

Any future feature or upgrade must check `AUDIT_FINDINGS.md` and this file before implementation. A blocked item is retried only when its external dependency is available; a rejected item needs new user evidence or a design change to reopen.
