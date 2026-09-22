from __future__ import annotations

import click
from rich.console import Console

from pyagenthound.config import DEFAULT_DB_PATH
from pyagenthound.graph.builder import build_graph
from pyagenthound.rules.engine import run_rules
from pyagenthound.storage.sqlite_store import SQLiteTraceStore

_SEVERITY_COLOR = {
    "CRITICAL": "bold red",
    "HIGH": "red",
    "MEDIUM": "yellow",
    "LOW": "dim",
}


@click.command("analyze")
@click.argument("trace_id")
@click.option("--db", "db_path", default=str(DEFAULT_DB_PATH), show_default=True)
def analyze_command(trace_id: str, db_path: str) -> None:
    """Run the deterministic rule engine against a captured trace and print findings.

    There is no root-cause engine yet (Phase 4) — this prints detected anomalies with
    their evidence, not a ranked "likely cause."
    """
    store = SQLiteTraceStore(db_path)
    trace = store.get_trace(trace_id)
    if trace is None:
        raise click.ClickException(f"trace {trace_id!r} not found in {db_path}")

    graph = build_graph(trace)
    findings = run_rules(trace, graph)

    console = Console()
    console.print(f"[bold]{trace.name}[/bold]  ({trace.trace_id})")
    console.print(f"status: {trace.status.value}   findings: {len(findings)}")

    if not findings:
        console.print(
            "\nNo deterministic findings. This means none of the built-in rules "
            "matched — it is not a claim that the trace is correct."
        )
        return

    for finding in findings:
        color = _SEVERITY_COLOR.get(finding.severity.value, "white")
        console.print(f"\n[{color}]{finding.severity.value}[/{color}]  {finding.title}")
        console.print(f"  {finding.description}")
        for evidence in finding.evidence:
            console.print(f"  evidence: {evidence.description}")
        console.print(f"  confidence: {finding.confidence:.2f}")
        if finding.recommendation:
            console.print(f"  recommendation: {finding.recommendation}")
