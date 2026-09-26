from __future__ import annotations

import click
from rich.console import Console

from pyagenthound.baseline.engine import compare_to_baseline, find_baseline
from pyagenthound.config import DEFAULT_DB_PATH
from pyagenthound.graph.builder import build_graph
from pyagenthound.rootcause.engine import rank_root_causes
from pyagenthound.rules.engine import run_rules
from pyagenthound.storage.sqlite_store import SQLiteTraceStore

_SEVERITY_COLOR = {
    "CRITICAL": "bold red",
    "HIGH": "red",
    "MEDIUM": "yellow",
    "LOW": "dim",
}

_LABEL_TEXT = {
    "likely_cause": "Likely cause",
    "contributing_factor": "Contributing factor",
}


@click.command("analyze")
@click.argument("trace_id")
@click.option("--db", "db_path", default=str(DEFAULT_DB_PATH), show_default=True)
def analyze_command(trace_id: str, db_path: str) -> None:
    """Run the deterministic rule engine + root-cause ranking against a captured
    trace and print findings and ranked hypotheses.

    If a prior successful execution of the same named trace exists in this
    database, it's used as a baseline (model/prompt/retriever/tool/latency/token
    changes become findings too) and feeds two of the root-cause confidence
    components (temporal_correlation, historical_frequency) — see
    docs/architecture.md section 6.
    """
    store = SQLiteTraceStore(db_path)
    trace = store.get_trace(trace_id)
    if trace is None:
        raise click.ClickException(f"trace {trace_id!r} not found in {db_path}")

    graph = build_graph(trace)
    findings = run_rules(trace, graph)

    baseline = find_baseline(store, trace)
    if baseline is not None:
        findings = [*findings, *compare_to_baseline(trace, baseline)]

    console = Console()
    console.print(f"[bold]{trace.name}[/bold]  ({trace.trace_id})")
    console.print(f"status: {trace.status.value}   findings: {len(findings)}")
    if baseline is not None:
        console.print(f"baseline: {baseline.trace_id} (most recent prior successful execution)")

    if not findings:
        console.print(
            "\nNo deterministic findings. This means none of the built-in rules "
            "matched — it is not a claim that the trace is correct."
        )
        return

    console.print("\n[bold]Findings[/bold]")
    for finding in findings:
        color = _SEVERITY_COLOR.get(finding.severity.value, "white")
        console.print(f"\n[{color}]{finding.severity.value}[/{color}]  {finding.title}")
        console.print(f"  {finding.description}")
        for evidence in finding.evidence:
            console.print(f"  evidence: {evidence.description}")
        console.print(f"  confidence: {finding.confidence:.2f}")
        if finding.recommendation:
            console.print(f"  recommendation: {finding.recommendation}")

    hypotheses = rank_root_causes(trace, graph, store=store)
    console.print("\n[bold]Root Cause Analysis[/bold] (deterministic estimate, not verified truth)")
    for hypothesis in hypotheses:
        label = _LABEL_TEXT[hypothesis.label]
        c = hypothesis.confidence_components
        parts = [
            f"evidence_strength={c.evidence_strength:.2f}",
            f"causal_proximity={c.causal_proximity:.2f}",
        ]
        if c.temporal_correlation is not None:
            parts.append(f"temporal_correlation={c.temporal_correlation:.2f}")
        if c.historical_frequency is not None:
            parts.append(f"historical_frequency={c.historical_frequency:.2f}")
        console.print(f"\n{label}: {hypothesis.statement}")
        console.print(f"  confidence: {hypothesis.confidence:.2f}  ({', '.join(parts)})")
        if hypothesis.recommendation:
            console.print(f"  recommendation: {hypothesis.recommendation}")
