"""SQLite implementation of TraceStore. See docs/architecture.md section 7."""

from __future__ import annotations

import json
import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path

from pyagenthound.sdk.models import (
    Event,
    Span,
    SpanError,
    SpanStatus,
    SpanType,
    Trace,
    TraceSummary,
)

_SCHEMA_PATH = Path(__file__).parent / "schema.sql"


def _dt_to_str(dt: datetime | None) -> str | None:
    return dt.isoformat() if dt is not None else None


def _parse_dt(s: str) -> datetime:
    return datetime.fromisoformat(s)


def _parse_dt_opt(s: str | None) -> datetime | None:
    return datetime.fromisoformat(s) if s is not None else None


class SQLiteTraceStore:
    """The only Phase-1 TraceStore implementation. Zero-config, single SQLite file."""

    def __init__(self, db_path: str | Path):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.init_schema()

    @contextmanager
    def _connect(self) -> Iterator[sqlite3.Connection]:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def init_schema(self) -> None:
        schema_sql = _SCHEMA_PATH.read_text()
        with self._connect() as conn:
            conn.executescript(schema_sql)

    def save_trace(self, trace: Trace) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO traces (trace_id, name, start_time, end_time, status, tags, metadata)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(trace_id) DO UPDATE SET
                    name=excluded.name, end_time=excluded.end_time, status=excluded.status,
                    tags=excluded.tags, metadata=excluded.metadata
                """,
                (
                    trace.trace_id,
                    trace.name,
                    _dt_to_str(trace.start_time),
                    _dt_to_str(trace.end_time),
                    trace.status.value,
                    json.dumps(trace.tags),
                    json.dumps(trace.metadata),
                ),
            )
            for span in trace.spans:
                conn.execute(
                    """
                    INSERT INTO spans (
                        span_id, trace_id, parent_span_id, name, span_type,
                        start_time, end_time, status, status_message,
                        attributes, events, input, output, error
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(span_id) DO UPDATE SET
                        parent_span_id=excluded.parent_span_id, name=excluded.name,
                        span_type=excluded.span_type, end_time=excluded.end_time,
                        status=excluded.status, status_message=excluded.status_message,
                        attributes=excluded.attributes, events=excluded.events,
                        input=excluded.input, output=excluded.output, error=excluded.error
                    """,
                    (
                        span.span_id,
                        span.trace_id,
                        span.parent_span_id,
                        span.name,
                        span.span_type.value,
                        _dt_to_str(span.start_time),
                        _dt_to_str(span.end_time),
                        span.status.value,
                        span.status_message,
                        json.dumps(span.attributes),
                        json.dumps([e.model_dump(mode="json") for e in span.events]),
                        json.dumps(span.input) if span.input is not None else None,
                        json.dumps(span.output) if span.output is not None else None,
                        json.dumps(span.error.model_dump(mode="json")) if span.error else None,
                    ),
                )

    def get_trace(self, trace_id: str) -> Trace | None:
        with self._connect() as conn:
            row = conn.execute("SELECT * FROM traces WHERE trace_id = ?", (trace_id,)).fetchone()
            if row is None:
                return None
            span_rows = conn.execute(
                "SELECT * FROM spans WHERE trace_id = ? ORDER BY start_time", (trace_id,)
            ).fetchall()
            spans = [_row_to_span(r) for r in span_rows]
            return Trace(
                trace_id=row["trace_id"],
                name=row["name"],
                start_time=_parse_dt(row["start_time"]),
                end_time=_parse_dt_opt(row["end_time"]),
                status=SpanStatus(row["status"]),
                tags=json.loads(row["tags"]),
                metadata=json.loads(row["metadata"]),
                spans=spans,
            )

    def list_traces(
        self,
        limit: int = 50,
        offset: int = 0,
        status: SpanStatus | None = None,
        name: str | None = None,
    ) -> list[TraceSummary]:
        query = """
            SELECT t.trace_id, t.name, t.start_time, t.end_time, t.status, t.tags,
                   (SELECT COUNT(*) FROM spans s WHERE s.trace_id = t.trace_id) AS span_count
            FROM traces t
        """
        conditions = []
        params: list[object] = []
        if status is not None:
            conditions.append("t.status = ?")
            params.append(status.value)
        if name is not None:
            conditions.append("t.name = ?")
            params.append(name)
        if conditions:
            query += " WHERE " + " AND ".join(conditions)
        query += " ORDER BY t.start_time DESC LIMIT ? OFFSET ?"
        params.extend([limit, offset])

        with self._connect() as conn:
            rows = conn.execute(query, params).fetchall()
            return [
                TraceSummary(
                    trace_id=r["trace_id"],
                    name=r["name"],
                    start_time=_parse_dt(r["start_time"]),
                    end_time=_parse_dt_opt(r["end_time"]),
                    status=SpanStatus(r["status"]),
                    tags=json.loads(r["tags"]),
                    span_count=r["span_count"],
                )
                for r in rows
            ]


def _row_to_span(row: sqlite3.Row) -> Span:
    events_raw = json.loads(row["events"])
    return Span(
        span_id=row["span_id"],
        trace_id=row["trace_id"],
        parent_span_id=row["parent_span_id"],
        name=row["name"],
        span_type=SpanType(row["span_type"]),
        start_time=_parse_dt(row["start_time"]),
        end_time=_parse_dt_opt(row["end_time"]),
        status=SpanStatus(row["status"]),
        status_message=row["status_message"],
        attributes=json.loads(row["attributes"]),
        events=[Event(**e) for e in events_raw],
        input=json.loads(row["input"]) if row["input"] is not None else None,
        output=json.loads(row["output"]) if row["output"] is not None else None,
        error=SpanError(**json.loads(row["error"])) if row["error"] is not None else None,
    )
