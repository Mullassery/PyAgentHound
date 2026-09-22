from __future__ import annotations

import click
from rich.console import Console
from rich.table import Table

from pyagenthound.config import DEFAULT_DB_PATH
from pyagenthound.storage.sqlite_store import SQLiteTraceStore


@click.command("inspect")
@click.argument("trace_id")
@click.option("--db", "db_path", default=str(DEFAULT_DB_PATH), show_default=True)
def inspect_command(trace_id: str, db_path: str) -> None:
    """Print a captured trace's spans/timeline/attributes."""
    store = SQLiteTraceStore(db_path)
    trace = store.get_trace(trace_id)
    if trace is None:
        raise click.ClickException(f"trace {trace_id!r} not found in {db_path}")

    console = Console()
    console.print(f"[bold]{trace.name}[/bold]  ({trace.trace_id})")
    duration = f"{trace.duration_ms:.1f}ms" if trace.duration_ms is not None else "in progress"
    console.print(f"status: {trace.status.value}   duration: {duration}")
    if trace.tags:
        console.print(f"tags: {', '.join(trace.tags)}")

    table = Table(show_header=True, header_style="bold")
    table.add_column("span")
    table.add_column("type")
    table.add_column("status")
    table.add_column("duration")
    table.add_column("parent")
    for span in trace.spans:
        span_duration = f"{span.duration_ms:.1f}ms" if span.duration_ms is not None else "-"
        table.add_row(
            span.name,
            span.span_type.value,
            span.status.value,
            span_duration,
            span.parent_span_id or "-",
        )
    console.print(table)

    for span in trace.spans:
        if span.attributes:
            console.print(f"\n[bold]{span.name}[/bold] attributes:")
            for key, value in span.attributes.items():
                console.print(f"  {key} = {value!r}")
        if span.error is not None:
            console.print(f"[red]{span.name} error: {span.error.type}: {span.error.message}[/red]")
