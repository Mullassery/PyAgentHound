"""Test case file I/O. See docs/architecture.md section 14.

Test cases live as JSON files on disk, not in the trace database — they're meant to
be committed to version control and run in CI (`pyagenthound test ./tests`), not
served.
"""

from __future__ import annotations

from pathlib import Path

from pyagenthound.evaluation.models import TestCase


def save_test_case(test_case: TestCase, path: Path) -> None:
    path.write_text(test_case.model_dump_json(indent=2) + "\n")


def load_test_case(path: Path) -> TestCase:
    return TestCase.model_validate_json(path.read_text())


def load_test_cases(directory: Path) -> list[TestCase]:
    return [load_test_case(p) for p in sorted(directory.glob("*.json"))]
