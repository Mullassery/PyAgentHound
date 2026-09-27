from __future__ import annotations

from pathlib import Path

import click
from rich.console import Console

from pyagenthound.config import DEFAULT_DB_PATH
from pyagenthound.evaluation.engine import evaluate
from pyagenthound.evaluation.io import load_test_cases
from pyagenthound.graph.builder import build_graph
from pyagenthound.rules.engine import run_rules
from pyagenthound.storage.sqlite_store import SQLiteTraceStore


@click.command("test")
@click.argument("tests_dir", type=click.Path(exists=True, file_okay=False, path_type=Path))
@click.option("--db", "db_path", default=str(DEFAULT_DB_PATH), show_default=True)
def test_command(tests_dir: Path, db_path: str) -> None:
    """Run assertion-based test cases (*.json files in TESTS_DIR) against captured
    traces. Test cases are hand-authored JSON (see docs/architecture.md section 14)
    referencing a trace_id already in the database — this does not re-run the agent,
    only re-checks assertions against what was captured.

    Exits non-zero if any test case fails, for CI gating.
    """
    store = SQLiteTraceStore(db_path)
    test_cases = load_test_cases(tests_dir)
    console = Console()

    if not test_cases:
        console.print(f"No test cases found in {tests_dir}")
        return

    all_passed = True
    for test_case in test_cases:
        trace = store.get_trace(test_case.trace_id)
        if trace is None:
            console.print(
                f"[red]ERROR[/red]  {test_case.name}: "
                f"trace {test_case.trace_id!r} not found in {db_path}"
            )
            all_passed = False
            continue

        graph = build_graph(trace)
        findings = run_rules(trace, graph)
        result = evaluate(trace, findings, test_case)
        all_passed = all_passed and result.passed

        status = "[green]PASS[/green]" if result.passed else "[red]FAIL[/red]"
        console.print(f"{status}  {result.name}")
        for assertion_result in result.assertions:
            if not assertion_result.passed:
                console.print(
                    f"  x {assertion_result.assertion.type.value}"
                    f"({assertion_result.assertion.target!r}): {assertion_result.message}"
                )

    console.print(f"\n{'all passed' if all_passed else 'some failed'}")
    if not all_passed:
        raise SystemExit(1)
