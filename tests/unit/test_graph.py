from pyagenthound.graph.builder import build_graph
from pyagenthound.graph.models import NodeType, Relationship
from pyagenthound.sdk.models import Span, SpanType, Trace


def _sample_trace() -> Trace:
    trace = Trace(name="req")
    agent = Span(trace_id=trace.trace_id, name="agent", span_type=SpanType.AGENT)
    retrieval = Span(
        trace_id=trace.trace_id,
        parent_span_id=agent.span_id,
        name="retrieval",
        span_type=SpanType.RETRIEVAL,
        attributes={"documents": ["policy-2024", {"id": "policy-2026", "date": "2026-01-01"}]},
    )
    llm = Span(
        trace_id=trace.trace_id, parent_span_id=agent.span_id, name="llm", span_type=SpanType.LLM
    )
    trace.spans = [agent, retrieval, llm]
    return trace


def test_build_graph_creates_root_and_span_nodes():
    trace = _sample_trace()
    graph = build_graph(trace)

    assert graph.trace_id == trace.trace_id
    assert graph.get_node(trace.trace_id) is not None
    assert graph.get_node(trace.trace_id).type == NodeType.TRACE  # type: ignore[union-attr]
    for span in trace.spans:
        node = graph.get_node(span.span_id)
        assert node is not None
        assert node.type == NodeType.from_span_type(span.span_type)


def test_build_graph_parent_edges_form_tree():
    trace = _sample_trace()
    agent, retrieval, llm = trace.spans
    graph = build_graph(trace)

    parent_edges = graph.edges_by_relationship(Relationship.PARENT)
    pairs = {(e.source, e.target) for e in parent_edges}

    assert (trace.trace_id, agent.span_id) in pairs
    assert (agent.span_id, retrieval.span_id) in pairs
    assert (agent.span_id, llm.span_id) in pairs


def test_dangling_parent_attaches_to_trace_root():
    trace = Trace(name="req")
    orphan = Span(
        trace_id=trace.trace_id,
        parent_span_id="does-not-exist",
        name="orphan",
        span_type=SpanType.TOOL,
    )
    trace.spans = [orphan]

    graph = build_graph(trace)

    parent_edges = graph.edges_by_relationship(Relationship.PARENT)
    assert (trace.trace_id, orphan.span_id) in {(e.source, e.target) for e in parent_edges}


def test_retrieval_extractor_creates_document_nodes_and_edges():
    trace = _sample_trace()
    _, retrieval, _ = trace.spans
    graph = build_graph(trace)

    doc_nodes = graph.nodes_by_type(NodeType.DOCUMENT)
    assert len(doc_nodes) == 2
    doc_ids = {n.id for n in doc_nodes}
    assert doc_ids == {"doc:policy-2024", "doc:policy-2026"}

    retrieves_edges = graph.edges_by_relationship(Relationship.RETRIEVES)
    assert len(retrieves_edges) == 2
    assert all(e.source == retrieval.span_id for e in retrieves_edges)

    dict_doc = graph.get_node("doc:policy-2026")
    assert dict_doc is not None
    assert dict_doc.attributes["date"] == "2026-01-01"


def test_neighbors_includes_both_directions():
    trace = _sample_trace()
    agent, retrieval, llm = trace.spans
    graph = build_graph(trace)

    neighbor_ids = {n.id for n in graph.neighbors(agent.span_id)}
    assert neighbor_ids == {trace.trace_id, retrieval.span_id, llm.span_id}


def test_ancestors_walks_back_through_retrieval_and_parent_edges():
    trace = _sample_trace()
    agent, retrieval, _ = trace.spans
    graph = build_graph(trace)

    doc_id = "doc:policy-2024"
    ancestor_ids = {n.id for n in graph.ancestors(doc_id)}
    assert ancestor_ids == {retrieval.span_id, agent.span_id, trace.trace_id}


def test_non_retrieval_span_produces_no_extra_nodes():
    trace = Trace(name="req")
    tool = Span(
        trace_id=trace.trace_id, name="tool", span_type=SpanType.TOOL, attributes={"args": {}}
    )
    trace.spans = [tool]

    graph = build_graph(trace)

    assert len(graph.nodes) == 2  # trace root + tool span, no extraction rule for TOOL yet
