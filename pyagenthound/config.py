"""Local config: where the default SQLite DB and config file live."""

from __future__ import annotations

from pathlib import Path

DEFAULT_HOME = Path.home() / ".pyagenthound"
DEFAULT_DB_PATH = DEFAULT_HOME / "pyagenthound.db"
DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 8787


def default_endpoint() -> str:
    return f"http://{DEFAULT_HOST}:{DEFAULT_PORT}"
