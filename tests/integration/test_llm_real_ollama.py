"""Exercises explain_root_cause against a real local Ollama instance.

Skipped automatically if Ollama isn't running — see product spec section 28: "No
tests should depend on a real external LLM API unless explicitly marked." This one
is explicitly marked, and only ever talks to localhost, never a paid cloud API.
"""

import socket

import pytest

from pyagenthound.graph.builder import build_graph
from pyagenthound.llm.explain import explain_root_cause
from pyagenthound.llm.providers import OllamaProvider
from pyagenthound.rootcause.engine import rank_root_causes
from pyagenthound.rules.engine import run_rules
from pyagenthound.sdk.models import Span, SpanType, Trace


def _ollama_available() -> bool:
    try:
        with socket.create_connection(("127.0.0.1", 11434), timeout=0.5):
            return True
    except OSError:
        return False


pytestmark = pytest.mark.skipif(not _ollama_available(), reason="Ollama not running on localhost")


def test_explain_root_cause_against_real_ollama():
    trace = Trace(name="customer-support-request")
    trace.spans = [
        Span(
            trace_id=trace.trace_id,
            name="retrieval",
            span_type=SpanType.RETRIEVAL,
            attributes={
                "documents": [
                    {"id": "policy-2024", "date": "2024-01-01"},
                    {"id": "policy-2025", "date": "2025-01-01"},
                    {"id": "policy-2026", "date": "2026-01-01"},
                ]
            },
        )
    ]
    graph = build_graph(trace)
    findings = run_rules(trace, graph)
    hypotheses = rank_root_causes(trace, graph, findings)

    explanation = explain_root_cause(findings, hypotheses, OllamaProvider())

    assert explanation.narrative
    assert explanation.provider == "ollama"
    valid_ids = {f.finding_id for f in findings}
    assert set(explanation.cited_finding_ids) <= valid_ids
