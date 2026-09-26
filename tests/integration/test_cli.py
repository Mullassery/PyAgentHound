from click.testing import CliRunner

from pyagenthound.cli.main import cli
from pyagenthound.sdk.models import Span, SpanStatus, SpanType, Trace
from pyagenthound.storage.sqlite_store import SQLiteTraceStore


def test_init_creates_db(tmp_path, monkeypatch):
    home = tmp_path / "home"
    monkeypatch.setattr("pyagenthound.cli.commands.init.DEFAULT_HOME", home)
    monkeypatch.setattr("pyagenthound.cli.commands.init.DEFAULT_DB_PATH", home / "pyagenthound.db")

    result = CliRunner().invoke(cli, ["init"])

    assert result.exit_code == 0
    assert (home / "pyagenthound.db").exists()


def test_inspect_prints_trace(tmp_path):
    db_path = tmp_path / "t.db"
    store = SQLiteTraceStore(db_path)
    trace = Trace(name="my-trace")
    store.save_trace(trace)

    result = CliRunner().invoke(cli, ["inspect", trace.trace_id, "--db", str(db_path)])

    assert result.exit_code == 0
    assert "my-trace" in result.output


def test_inspect_missing_trace_errors(tmp_path):
    db_path = tmp_path / "t.db"
    SQLiteTraceStore(db_path)

    result = CliRunner().invoke(cli, ["inspect", "nonexistent", "--db", str(db_path)])

    assert result.exit_code != 0


def test_analyze_prints_findings(tmp_path):
    db_path = tmp_path / "t.db"
    store = SQLiteTraceStore(db_path)
    trace = Trace(name="my-trace")
    trace.spans.append(
        Span(
            trace_id=trace.trace_id,
            name="retrieval",
            span_type=SpanType.RETRIEVAL,
            attributes={"documents": []},
        )
    )
    store.save_trace(trace)

    result = CliRunner().invoke(cli, ["analyze", trace.trace_id, "--db", str(db_path)])

    assert result.exit_code == 0
    assert "Retrieval returned no documents" in result.output
    assert "Root Cause Analysis" in result.output
    assert "Likely cause" in result.output


def test_analyze_no_findings(tmp_path):
    db_path = tmp_path / "t.db"
    store = SQLiteTraceStore(db_path)
    trace = Trace(name="clean-trace")
    store.save_trace(trace)

    result = CliRunner().invoke(cli, ["analyze", trace.trace_id, "--db", str(db_path)])

    assert result.exit_code == 0
    assert "No deterministic findings" in result.output


def test_analyze_missing_trace_errors(tmp_path):
    db_path = tmp_path / "t.db"
    SQLiteTraceStore(db_path)

    result = CliRunner().invoke(cli, ["analyze", "nonexistent", "--db", str(db_path)])

    assert result.exit_code != 0


def test_analyze_shows_baseline_comparison(tmp_path):
    db_path = tmp_path / "t.db"
    store = SQLiteTraceStore(db_path)

    baseline = Trace(name="checkout", status=SpanStatus.OK)
    baseline.spans.append(
        Span(
            trace_id=baseline.trace_id,
            name="llm",
            span_type=SpanType.LLM,
            attributes={"model": "gpt-4o"},
        )
    )
    store.save_trace(baseline)

    current = Trace(name="checkout", status=SpanStatus.ERROR)
    current.spans.append(
        Span(
            trace_id=current.trace_id,
            name="llm",
            span_type=SpanType.LLM,
            attributes={"model": "gpt-4-turbo"},
        )
    )
    store.save_trace(current)

    result = CliRunner().invoke(cli, ["analyze", current.trace_id, "--db", str(db_path)])

    assert result.exit_code == 0
    assert f"baseline: {baseline.trace_id}" in result.output
    assert "Model changed" in result.output
    assert "temporal_correlation" in result.output
