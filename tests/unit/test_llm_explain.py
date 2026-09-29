import json

import pytest

from pyagenthound.graph.builder import build_graph
from pyagenthound.llm.explain import LLMOutputValidationError, explain_root_cause
from pyagenthound.rootcause.engine import rank_root_causes
from pyagenthound.rules.engine import run_rules
from pyagenthound.sdk.models import Span, SpanType, Trace


class _FakeProvider:
    name = "fake"
    model = "fake-model"

    def __init__(self, response: str):
        self._response = response

    def complete(self, system: str, user: str) -> str:
        return self._response


def _findings_and_hypotheses():
    trace = Trace(name="t")
    trace.spans = [
        Span(
            trace_id=trace.trace_id,
            name="retrieval",
            span_type=SpanType.RETRIEVAL,
            attributes={"documents": []},
        )
    ]
    graph = build_graph(trace)
    findings = run_rules(trace, graph)
    hypotheses = rank_root_causes(trace, graph, findings)
    return findings, hypotheses


def test_explain_root_cause_returns_grounded_explanation():
    findings, hypotheses = _findings_and_hypotheses()
    real_id = findings[0].finding_id
    provider = _FakeProvider(
        json.dumps({"narrative": "Retrieval returned nothing.", "cited_finding_ids": [real_id]})
    )

    explanation = explain_root_cause(findings, hypotheses, provider)

    assert explanation.narrative == "Retrieval returned nothing."
    assert explanation.cited_finding_ids == [real_id]
    assert explanation.provider == "fake"
    assert explanation.model == "fake-model"


def test_explain_root_cause_rejects_unsupported_citation():
    findings, hypotheses = _findings_and_hypotheses()
    provider = _FakeProvider(
        json.dumps({"narrative": "Made up.", "cited_finding_ids": ["finding_does_not_exist"]})
    )

    with pytest.raises(LLMOutputValidationError, match="not present"):
        explain_root_cause(findings, hypotheses, provider)


def test_explain_root_cause_rejects_invalid_json():
    findings, hypotheses = _findings_and_hypotheses()
    provider = _FakeProvider("not json at all")

    with pytest.raises(LLMOutputValidationError, match="valid JSON"):
        explain_root_cause(findings, hypotheses, provider)


def test_explain_root_cause_rejects_missing_fields():
    findings, hypotheses = _findings_and_hypotheses()
    provider = _FakeProvider(json.dumps({"narrative": "missing citations field"}))

    with pytest.raises(LLMOutputValidationError, match="missing required fields"):
        explain_root_cause(findings, hypotheses, provider)


def test_explain_root_cause_rejects_non_string_citations():
    findings, hypotheses = _findings_and_hypotheses()
    provider = _FakeProvider(json.dumps({"narrative": "x", "cited_finding_ids": [123]}))

    with pytest.raises(LLMOutputValidationError, match="must be strings"):
        explain_root_cause(findings, hypotheses, provider)


def test_explain_root_cause_requires_findings():
    provider = _FakeProvider(json.dumps({"narrative": "x", "cited_finding_ids": []}))

    with pytest.raises(ValueError, match="no findings"):
        explain_root_cause([], [], provider)
