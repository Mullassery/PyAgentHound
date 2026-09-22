from __future__ import annotations

import click

from pyagenthound.config import DEFAULT_DB_PATH, DEFAULT_HOME
from pyagenthound.storage.sqlite_store import SQLiteTraceStore


@click.command("init")
def init_command() -> None:
    """Initialize local PyAgentHound config + database."""
    DEFAULT_HOME.mkdir(parents=True, exist_ok=True)
    SQLiteTraceStore(DEFAULT_DB_PATH)  # creates schema as a side effect
    click.echo(f"Initialized PyAgentHound at {DEFAULT_HOME}")
    click.echo(f"  database: {DEFAULT_DB_PATH}")
