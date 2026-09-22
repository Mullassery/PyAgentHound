"""Built-in deterministic rules. See docs/architecture.md section 5.

Five rules ship in Phase 3, chosen to prove the rule-engine pattern across more than
one `FailureCategory` rather than exhaustively covering the product spec's full rule
list (section 6.5) — the remaining rules there are documented future work in
ROADMAP_HONEST.md, added the same way: a class with `id`/`category`/`evaluate`.
"""

from __future__ import annotations

from collections import Counter
from datetime import date, datetime
from typing import Any

from pyagenthound.graph.models import ExecutionGraph
from pyagenthound.rules.models import Evidence, FailureCategory, Finding, Severity
from pyagenthound.sdk.models import SpanStatus, SpanType, Trace


def _parse_date(value: Any) -> datetime | None:
    if not isinstance(value, str):
        return None
    try:
        return datetime.fromisoformat(value)
    except ValueError:
        pass
    try:
        parsed = date.fromisoformat(value)
        return datetime(parsed.year, parsed.month, parsed.day)
    except ValueError:
        return None


class EmptyRetrievalRule:
    id = "empty_retrieval"
    category = FailureCategory.RETRIEVAL_FAILURE

    def evaluate(self, trace: Trace, graph: ExecutionGraph) -> list[Finding]:
        findings = []
        for span in trace.spans:
            if span.span_type != SpanType.RETRIEVAL:
                continue
            documents = span.attributes.get("documents")
            if isinstance(documents, list) and len(documents) == 0:
                findings.append(
                    Finding(
                        rule_id=self.id,
                        category=self.category,
                        severity=Severity.HIGH,
                        title="Retrieval returned no documents",
                        description=f"Retrieval span {span.name!r} returned zero documents.",
                        evidence=[
                            Evidence(
                                description="documents attribute is an empty list",
                                data={
                                    "span_id": span.span_id,
                                    "query": span.attributes.get("query"),
                                },
                            )
                        ],
                        affected_nodes=[span.span_id],
                        confidence=1.0,
                        recommendation=(
                            "Check retriever configuration, index freshness, and query relevance."
                        ),
                    )
                )
        return findings


class StaleRetrievalDocumentsRule:
    """Flags retrieved documents that predate the newest document retrieved for the
    same query — the deterministic signal behind the stale-context demo scenario
    (product spec section 27). Compares dates *within* one retrieval, not against an
    external "active version" (no such baseline exists yet — see Phase 4).
    """

    id = "stale_retrieval_documents"
    category = FailureCategory.RETRIEVAL_FAILURE

    def evaluate(self, trace: Trace, graph: ExecutionGraph) -> list[Finding]:
        findings = []
        for span in trace.spans:
            if span.span_type != SpanType.RETRIEVAL:
                continue
            documents = span.attributes.get("documents")
            if not isinstance(documents, list):
                continue

            dated: list[tuple[dict[str, Any], datetime]] = []
            for doc in documents:
                if not isinstance(doc, dict):
                    continue
                parsed = _parse_date(doc.get("date"))
                if parsed is not None:
                    dated.append((doc, parsed))
            if len(dated) < 2:
                continue

            newest = max(dt for _, dt in dated)
            stale = [(doc, dt) for doc, dt in dated if dt < newest]
            if not stale:
                continue

            ratio = len(stale) / len(dated)
            severity = Severity.HIGH if ratio >= 0.5 else Severity.MEDIUM
            findings.append(
                Finding(
                    rule_id=self.id,
                    category=self.category,
                    severity=severity,
                    title="Retrieved documents include stale versions",
                    description=(
                        f"{len(stale)} of {len(dated)} dated documents retrieved by "
                        f"{span.name!r} predate the most recently dated document "
                        "retrieved for the same query."
                    ),
                    evidence=[
                        Evidence(
                            description=(
                                f"document {doc.get('id', '?')} dated {dt.isoformat()}, "
                                f"newest retrieved is dated {newest.isoformat()}"
                            ),
                            data={"document": doc, "span_id": span.span_id},
                        )
                        for doc, dt in stale
                    ],
                    affected_nodes=[span.span_id]
                    + [f"doc:{doc['id']}" for doc, _ in stale if "id" in doc],
                    confidence=round(min(0.5 + ratio, 0.95), 2),
                    recommendation=(
                        "Add a freshness filter or version-aware ranking boost so "
                        "retrieval prefers the most recent document version."
                    ),
                )
            )
        return findings


class DuplicateRetrievedDocumentsRule:
    id = "duplicate_retrieved_documents"
    category = FailureCategory.RETRIEVAL_FAILURE

    def evaluate(self, trace: Trace, graph: ExecutionGraph) -> list[Finding]:
        findings = []
        for span in trace.spans:
            if span.span_type != SpanType.RETRIEVAL:
                continue
            documents = span.attributes.get("documents")
            if not isinstance(documents, list) or not documents:
                continue

            ids = [doc.get("id") if isinstance(doc, dict) else doc for doc in documents]
            counts = Counter(doc_id for doc_id in ids if doc_id is not None)
            duplicates = {doc_id: count for doc_id, count in counts.items() if count > 1}
            if not duplicates:
                continue

            findings.append(
                Finding(
                    rule_id=self.id,
                    category=self.category,
                    severity=Severity.LOW,
                    title="Retrieval returned duplicate documents",
                    description=(
                        f"{len(duplicates)} document id(s) appear more than once "
                        f"among the {len(documents)} documents retrieved by {span.name!r}."
                    ),
                    evidence=[
                        Evidence(
                            description=f"document {doc_id!r} appears {count} times",
                            data={"document_id": doc_id, "count": count},
                        )
                        for doc_id, count in duplicates.items()
                    ],
                    affected_nodes=[span.span_id],
                    confidence=1.0,
                    recommendation=(
                        "Deduplicate retrieved documents before building the model context."
                    ),
                )
            )
        return findings


class ToolFailureRule:
    id = "tool_failure"
    category = FailureCategory.TOOL_FAILURE

    def evaluate(self, trace: Trace, graph: ExecutionGraph) -> list[Finding]:
        findings = []
        for span in trace.spans:
            if span.span_type not in (SpanType.TOOL, SpanType.MCP):
                continue
            if span.status != SpanStatus.ERROR:
                continue
            findings.append(
                Finding(
                    rule_id=self.id,
                    category=self.category,
                    severity=Severity.HIGH,
                    title=f"Tool call failed: {span.name}",
                    description=(
                        span.error.message
                        if span.error
                        else f"{span.name} ended with ERROR status."
                    ),
                    evidence=[
                        Evidence(
                            description="span status is ERROR",
                            data={
                                "span_id": span.span_id,
                                "error": span.error.model_dump() if span.error else None,
                            },
                        )
                    ],
                    affected_nodes=[span.span_id],
                    confidence=1.0,
                    recommendation=(
                        "Inspect the tool's arguments and downstream service for the "
                        "root cause of the failure."
                    ),
                )
            )
        return findings


class DanglingParentSpanRule:
    id = "dangling_parent_span"
    category = FailureCategory.CONFIGURATION_FAILURE

    def evaluate(self, trace: Trace, graph: ExecutionGraph) -> list[Finding]:
        findings = []
        span_ids = {span.span_id for span in trace.spans}
        for span in trace.spans:
            if span.parent_span_id is None or span.parent_span_id in span_ids:
                continue
            findings.append(
                Finding(
                    rule_id=self.id,
                    category=self.category,
                    severity=Severity.MEDIUM,
                    title="Span references a missing parent",
                    description=(
                        f"Span {span.name!r} has parent_span_id={span.parent_span_id!r}, "
                        "which is not present in this trace."
                    ),
                    evidence=[
                        Evidence(
                            description="parent_span_id not found among the trace's spans",
                            data={"span_id": span.span_id, "parent_span_id": span.parent_span_id},
                        )
                    ],
                    affected_nodes=[span.span_id],
                    confidence=1.0,
                    recommendation=(
                        "Check for dropped spans (sampling, export failures) or an "
                        "incorrect manually-assigned parent_span_id."
                    ),
                )
            )
        return findings
