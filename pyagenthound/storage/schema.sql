CREATE TABLE IF NOT EXISTS traces (
    trace_id   TEXT PRIMARY KEY,
    name       TEXT NOT NULL,
    start_time TEXT NOT NULL,
    end_time   TEXT,
    status     TEXT NOT NULL,
    tags       TEXT NOT NULL DEFAULT '[]',
    metadata   TEXT NOT NULL DEFAULT '{}'
);

CREATE TABLE IF NOT EXISTS spans (
    span_id        TEXT PRIMARY KEY,
    trace_id       TEXT NOT NULL REFERENCES traces(trace_id),
    parent_span_id TEXT,
    name           TEXT NOT NULL,
    span_type      TEXT NOT NULL,
    start_time     TEXT NOT NULL,
    end_time       TEXT,
    status         TEXT NOT NULL,
    status_message TEXT,
    attributes     TEXT NOT NULL DEFAULT '{}',
    events         TEXT NOT NULL DEFAULT '[]',
    input          TEXT,
    output         TEXT,
    error          TEXT
);

CREATE INDEX IF NOT EXISTS idx_spans_trace_id ON spans(trace_id);
CREATE INDEX IF NOT EXISTS idx_traces_start_time ON traces(start_time);
