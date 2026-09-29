"""LLM-powered explanation. See docs/architecture.md section 16.

Strictly additive and optional (design principles 7-8): this never replaces the
deterministic rule/root-cause engines, only asks a model to narrate what they
already found, in plain English, for a human. The LLM is given *only* the structured
evidence already computed — `finding_id`, category, severity, title, description,
evidence, confidence, recommendation for each finding, and label/statement/
confidence for each ranked hypothesis. It never sees the raw trace and is never
asked to detect anything new. Every citation in its response is validated against
the real `finding_id`s it was given; a citation that doesn't exist is a hard
failure, not silently dropped — product spec section 7: "Reject unsupported claims."
"""

from __future__ import annotations

import json

from pydantic import BaseModel

from pyagenthound.llm.providers import LLMProvider
from pyagenthound.rootcause.models import RootCauseHypothesis
from pyagenthound.rules.models import Finding

_SYSTEM_PROMPT = """You are explaining an AI system's debugging findings to a human engineer.
You will be given a JSON object with findings and ranked root-cause hypotheses that were
already computed by deterministic rules -- you are not detecting anything new, only
narrating what is already there.

Rules you MUST follow:
- Only reference finding_ids that appear in the input. Never invent a finding_id.
- Never state a fact that isn't present in the input evidence.
- Never assign your own confidence number -- use the ones given.
- Respond with ONLY a JSON object, no other text: {"narrative": "<2-4 sentence
  plain-English summary>", "cited_finding_ids": ["<finding_id>", ...]}.
  cited_finding_ids must list every finding_id your narrative refers to.
"""


class LLMExplanation(BaseModel):
    narrative: str
    cited_finding_ids: list[str]
    provider: str
    model: str


class LLMOutputValidationError(RuntimeError):
    """Raised when the LLM's response is malformed or cites evidence that doesn't exist."""


def explain_root_cause(
    findings: list[Finding],
    hypotheses: list[RootCauseHypothesis],
    provider: LLMProvider,
) -> LLMExplanation:
    if not findings:
        raise ValueError("no findings to explain")

    payload = {
        "findings": [
            {
                "finding_id": f.finding_id,
                "rule_id": f.rule_id,
                "category": f.category.value,
                "severity": f.severity.value,
                "title": f.title,
                "description": f.description,
                "evidence": [e.description for e in f.evidence],
                "confidence": f.confidence,
                "recommendation": f.recommendation,
            }
            for f in findings
        ],
        "hypotheses": [
            {
                "label": h.label,
                "statement": h.statement,
                "finding_id": h.finding_id,
                "confidence": h.confidence,
            }
            for h in hypotheses
        ],
    }

    raw = provider.complete(_SYSTEM_PROMPT, json.dumps(payload))

    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise LLMOutputValidationError(f"LLM did not return valid JSON: {raw!r}") from exc

    narrative = parsed.get("narrative")
    cited = parsed.get("cited_finding_ids")
    if not isinstance(narrative, str) or not isinstance(cited, list):
        raise LLMOutputValidationError(f"LLM response missing required fields: {parsed!r}")
    if not all(isinstance(c, str) for c in cited):
        raise LLMOutputValidationError(f"cited_finding_ids must be strings: {cited!r}")

    valid_ids = {f.finding_id for f in findings}
    unsupported = [c for c in cited if c not in valid_ids]
    if unsupported:
        raise LLMOutputValidationError(
            f"LLM cited finding_id(s) not present in the provided evidence: {unsupported}"
        )

    return LLMExplanation(
        narrative=narrative,
        cited_finding_ids=cited,
        provider=provider.name,
        model=getattr(provider, "model", "unknown"),
    )
