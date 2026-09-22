"""Execution graph domain model. See docs/architecture.md section 4.

A trace's spans already form a tree via `parent_span_id`. The execution graph is a
superset of that tree: nodes are spans (or entities extracted from span attributes,
e.g. retrieved documents) and edges carry a typed relationship, not just parent/child.
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field

from pyagenthound.sdk.models import SpanStatus, SpanType


class NodeType(str, Enum):
    TRACE = "TRACE"
    AGENT = "AGENT"
    LLM = "LLM"
    RETRIEVAL = "RETRIEVAL"
    EMBEDDING = "EMBEDDING"
    RERANKING = "RERANKING"
    TOOL = "TOOL"
    MCP = "MCP"
    API = "API"
    DATABASE = "DATABASE"
    VECTOR_DB = "VECTOR_DB"
    PROMPT = "PROMPT"
    MEMORY = "MEMORY"
    GUARDRAIL = "GUARDRAIL"
    EVALUATION = "EVALUATION"
    CUSTOM = "CUSTOM"
    DOCUMENT = "DOCUMENT"

    @classmethod
    def from_span_type(cls, span_type: SpanType) -> NodeType:
        return cls(span_type.value)


class Relationship(str, Enum):
    PARENT = "PARENT"
    CALLS = "CALLS"
    DEPENDS_ON = "DEPENDS_ON"
    PRODUCES = "PRODUCES"
    CONSUMES = "CONSUMES"
    RETRIEVES = "RETRIEVES"
    INVOKES = "INVOKES"
    TRANSFORMS = "TRANSFORMS"


class Node(BaseModel):
    id: str
    type: NodeType
    name: str
    timestamp: datetime | None = None
    duration_ms: float | None = None
    attributes: dict[str, Any] = Field(default_factory=dict)
    status: SpanStatus | None = None


class Edge(BaseModel):
    source: str
    target: str
    relationship: Relationship


class ExecutionGraph(BaseModel):
    trace_id: str
    nodes: list[Node] = Field(default_factory=list)
    edges: list[Edge] = Field(default_factory=list)

    def get_node(self, node_id: str) -> Node | None:
        return next((n for n in self.nodes if n.id == node_id), None)

    def nodes_by_type(self, node_type: NodeType) -> list[Node]:
        return [n for n in self.nodes if n.type == node_type]

    def edges_by_relationship(self, relationship: Relationship) -> list[Edge]:
        return [e for e in self.edges if e.relationship == relationship]

    def nodes_in_window(self, start: datetime, end: datetime) -> list[Node]:
        return [n for n in self.nodes if n.timestamp is not None and start <= n.timestamp <= end]

    def outgoing(self, node_id: str, relationship: Relationship | None = None) -> list[Edge]:
        return [
            e
            for e in self.edges
            if e.source == node_id and (relationship is None or e.relationship == relationship)
        ]

    def incoming(self, node_id: str, relationship: Relationship | None = None) -> list[Edge]:
        return [
            e
            for e in self.edges
            if e.target == node_id and (relationship is None or e.relationship == relationship)
        ]

    def neighbors(self, node_id: str, relationship: Relationship | None = None) -> list[Node]:
        ids = {e.target for e in self.outgoing(node_id, relationship)}
        ids |= {e.source for e in self.incoming(node_id, relationship)}
        return [n for n in self.nodes if n.id in ids]

    def ancestors(self, node_id: str) -> list[Node]:
        """Walk incoming edges transitively — backward lineage (product spec section 13)."""
        seen: set[str] = set()
        result: list[Node] = []
        frontier = [node_id]
        while frontier:
            current = frontier.pop()
            for edge in self.incoming(current):
                if edge.source in seen:
                    continue
                seen.add(edge.source)
                node = self.get_node(edge.source)
                if node is not None:
                    result.append(node)
                frontier.append(edge.source)
        return result
