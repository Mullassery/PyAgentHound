"""Trace export. See docs/architecture.md section 7.

Local-first: `LocalSQLiteExporter` is the default (no server required).
`HTTPExporter` is used only when the caller explicitly configures an `endpoint`.
Export failures are always caught and logged — instrumentation must never crash
the host application.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Protocol

import requests

from pyagenthound.sdk.models import Trace

logger = logging.getLogger("pyagenthound")


class Exporter(Protocol):
    def export(self, trace: Trace) -> None: ...


class LocalSQLiteExporter:
    """Writes completed traces straight to a local SQLite file."""

    def __init__(self, db_path: str | Path):
        from pyagenthound.storage.sqlite_store import SQLiteTraceStore

        self._store = SQLiteTraceStore(db_path)

    def export(self, trace: Trace) -> None:
        try:
            self._store.save_trace(trace)
        except Exception:
            logger.warning(
                "pyagenthound: failed to write trace %s to local storage",
                trace.trace_id,
                exc_info=True,
            )


class HTTPExporter:
    """POSTs completed traces to a running `pyagenthound serve` instance."""

    def __init__(self, endpoint: str, timeout: float = 5.0):
        self.endpoint = endpoint.rstrip("/")
        self.timeout = timeout

    def export(self, trace: Trace) -> None:
        try:
            resp = requests.post(
                f"{self.endpoint}/api/traces",
                data=trace.model_dump_json(),
                headers={"Content-Type": "application/json"},
                timeout=self.timeout,
            )
            resp.raise_for_status()
        except Exception:
            logger.warning(
                "pyagenthound: failed to export trace %s to %s",
                trace.trace_id,
                self.endpoint,
                exc_info=True,
            )
