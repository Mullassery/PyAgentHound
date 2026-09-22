"""Execution graph construction from a Trace. See docs/architecture.md section 4.

`build_graph` walks a trace's spans into a `TRACE` root node + one node per span,
linked by `PARENT` edges (the structural tree already implicit in `parent_span_id`).
On top of that, a small per-`SpanType` extractor registry pulls additional
nodes/edges out of span attributes — Phase 2 ships exactly one extractor
(`RETRIEVAL` -> `DOCUMENT` nodes via `RETRIEVES` edges, the basis for data/context
lineage in product spec section 13). Extractors for other span types (tool
arguments, MCP resources, etc.) are a documented future extension, added the same
way via `@_register(SpanType.X)` — not built yet, not stubbed.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from pyagenthound.graph.models import Edge, ExecutionGraph, Node, NodeType, Relationship
from pyagenthound.sdk.models import Span, SpanType, Trace


def build_graph(trace: Trace) -> ExecutionGraph:
    graph = ExecutionGraph(trace_id=trace.trace_id)
    graph.nodes.append(
        Node(
            id=trace.trace_id,
            type=NodeType.TRACE,
            name=trace.name,
            timestamp=trace.start_time,
            duration_ms=trace.duration_ms,
            attributes=trace.metadata,
            status=trace.status,
        )
    )

    span_ids = {span.span_id for span in trace.spans}
    for span in trace.spans:
        graph.nodes.append(_span_to_node(span))

        parent_id = span.parent_span_id if span.parent_span_id in span_ids else trace.trace_id
        graph.edges.append(
            Edge(source=parent_id, target=span.span_id, relationship=Relationship.PARENT)
        )

        _extract(span, graph)

    return graph


def _span_to_node(span: Span) -> Node:
    return Node(
        id=span.span_id,
        type=NodeType.from_span_type(span.span_type),
        name=span.name,
        timestamp=span.start_time,
        duration_ms=span.duration_ms,
        attributes=span.attributes,
        status=span.status,
    )


_Extractor = Callable[[Span, ExecutionGraph], None]
_EXTRACTORS: dict[SpanType, _Extractor] = {}


def _register(span_type: SpanType) -> Callable[[_Extractor], _Extractor]:
    def decorator(fn: _Extractor) -> _Extractor:
        _EXTRACTORS[span_type] = fn
        return fn

    return decorator


def _extract(span: Span, graph: ExecutionGraph) -> None:
    extractor = _EXTRACTORS.get(span.span_type)
    if extractor is not None:
        extractor(span, graph)


@_register(SpanType.RETRIEVAL)
def _extract_retrieval_documents(span: Span, graph: ExecutionGraph) -> None:
    documents = span.attributes.get("documents")
    if not isinstance(documents, list):
        return
    for index, doc in enumerate(documents):
        doc_id = _document_id(span.span_id, index, doc)
        if isinstance(doc, dict):
            name = str(doc.get("id", doc_id))
            attributes = doc
        else:
            name = str(doc)
            attributes = {"value": doc}
        doc_node = Node(id=doc_id, type=NodeType.DOCUMENT, name=name, attributes=attributes)
        graph.nodes.append(doc_node)
        graph.edges.append(
            Edge(source=span.span_id, target=doc_id, relationship=Relationship.RETRIEVES)
        )


def _document_id(span_id: str, index: int, doc: Any) -> str:
    if isinstance(doc, dict) and "id" in doc:
        return f"doc:{doc['id']}"
    if isinstance(doc, str):
        return f"doc:{doc}"
    return f"doc:{span_id}:{index}"
