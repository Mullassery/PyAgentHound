from __future__ import annotations

import json
from typing import Any

import click
from rich.console import Console

from pyagenthound.config import DEFAULT_DB_PATH
from pyagenthound.replay.engine import UnsafeReplayError, run_replay
from pyagenthound.storage.sqlite_store import SQLiteTraceStore


def _parse_value(raw: str) -> Any:
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return raw


@click.command("replay")
@click.argument("trace_id")
@click.option(
    "--set",
    "overrides_raw",
    multiple=True,
    metavar="NAME.KEY=VALUE",
    help="Override an attribute on every span named NAME. VALUE is parsed as JSON "
    "if possible, else kept as a string. Repeatable.",
)
@click.option(
    "--allow-unsafe",
    is_flag=True,
    default=False,
    help="Confirm overriding a non-READ_ONLY span (TOOL, MCP, unannotated spans, etc.).",
)
@click.option("--db", "db_path", default=str(DEFAULT_DB_PATH), show_default=True)
def replay_command(
    trace_id: str, overrides_raw: tuple[str, ...], allow_unsafe: bool, db_path: str
) -> None:
    """Replay a captured trace with attribute overrides and compare findings.

    This clones the trace and edits span attributes — it does not re-invoke the
    original agent, model, or tools. It answers "if retrieval had returned X instead,
    would this finding go away?", not "what would actually happen if I ran this
    again?"
    """
    store = SQLiteTraceStore(db_path)
    trace = store.get_trace(trace_id)
    if trace is None:
        raise click.ClickException(f"trace {trace_id!r} not found in {db_path}")

    overrides_by_name: dict[str, dict[str, Any]] = {}
    for raw in overrides_raw:
        name_and_key, _, value_raw = raw.partition("=")
        name, _, key = name_and_key.partition(".")
        if not name or not key:
            raise click.ClickException(f"--set value must look like NAME.KEY=VALUE, got {raw!r}")
        overrides_by_name.setdefault(name, {})[key] = _parse_value(value_raw)

    overrides_by_span_id = {
        span.span_id: overrides_by_name[span.name]
        for span in trace.spans
        if span.name in overrides_by_name
    }

    try:
        result = run_replay(store, trace, overrides_by_span_id, allow_unsafe=allow_unsafe)
    except UnsafeReplayError as exc:
        raise click.ClickException(f"{exc} (pass --allow-unsafe to confirm)") from exc

    console = Console()
    console.print(f"[bold]Replayed[/bold] {trace.trace_id} -> {result.replayed_trace_id}")
    console.print(
        f"original findings: {len(result.original_findings)}   "
        f"replayed findings: {len(result.replayed_findings)}"
    )
    if result.resolved_rule_ids:
        console.print(f"[green]resolved:[/green] {', '.join(result.resolved_rule_ids)}")
    if result.new_rule_ids:
        console.print(f"[red]new findings introduced:[/red] {', '.join(result.new_rule_ids)}")
    if not result.resolved_rule_ids and not result.new_rule_ids:
        console.print("no change in which rules fired")
    console.print("\ninspect the replayed trace with:")
    console.print(f"  pyagenthound inspect {result.replayed_trace_id}")
