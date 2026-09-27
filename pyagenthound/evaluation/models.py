"""Evaluation domain model. See docs/architecture.md section 14.

Test cases are declarative assertions about a trace, not a way to actually re-invoke
the agent under different conditions (see docs/architecture.md section 13 for why
PyAgentHound can't honestly do that). They're meant to be authored from a real,
already-captured trace (`pyagenthound analyze` shows you what's true about it), saved
as a JSON file, committed to version control, and re-checked whenever that trace_id's
data changes or as a template for a fresh trace_id after a fix.
"""

from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, Field


class AssertionType(str, Enum):
    STATUS_OK = "STATUS_OK"
    OUTPUT_CONTAINS = "OUTPUT_CONTAINS"
    NO_FINDING = "NO_FINDING"
    SPAN_EXISTS = "SPAN_EXISTS"
    NO_TOOL_CALLED = "NO_TOOL_CALLED"


class Assertion(BaseModel):
    type: AssertionType
    target: str | None = None
    """Meaning depends on `type`: a substring (OUTPUT_CONTAINS), a rule_id or
    category (NO_FINDING), a span name (SPAN_EXISTS), a tool name (NO_TOOL_CALLED).
    Unused for STATUS_OK."""


class TestCase(BaseModel):
    __test__ = False  # tell pytest this isn't a test class to collect

    name: str
    trace_id: str
    assertions: list[Assertion] = Field(default_factory=list)


class AssertionResult(BaseModel):
    assertion: Assertion
    passed: bool
    message: str


class TestCaseResult(BaseModel):
    __test__ = False  # tell pytest this isn't a test class to collect

    name: str
    trace_id: str
    passed: bool
    assertions: list[AssertionResult] = Field(default_factory=list)
