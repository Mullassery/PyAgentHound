from click.testing import CliRunner

from pyagenthound.cli.main import cli
from pyagenthound.evaluation.io import save_test_case
from pyagenthound.evaluation.models import Assertion, AssertionType, TestCase
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


def test_replay_resolves_finding(tmp_path):
    db_path = tmp_path / "t.db"
    store = SQLiteTraceStore(db_path)
    trace = Trace(name="req")
    retrieval = Span(
        trace_id=trace.trace_id,
        name="retrieval",
        span_type=SpanType.RETRIEVAL,
        attributes={
            "documents": [
                {"id": "a", "date": "2024-01-01"},
                {"id": "b", "date": "2026-01-01"},
            ]
        },
    )
    trace.spans.append(retrieval)
    store.save_trace(trace)

    result = CliRunner().invoke(
        cli,
        [
            "replay",
            trace.trace_id,
            "--set",
            'retrieval.documents=[{"id": "b", "date": "2026-01-01"}]',
            "--db",
            str(db_path),
        ],
    )

    assert result.exit_code == 0
    assert "resolved" in result.output
    assert "stale_retrieval_documents" in result.output


def test_replay_requires_confirmation_for_unsafe_override(tmp_path):
    db_path = tmp_path / "t.db"
    store = SQLiteTraceStore(db_path)
    trace = Trace(name="req")
    tool = Span(trace_id=trace.trace_id, name="tool", span_type=SpanType.TOOL)
    trace.spans.append(tool)
    store.save_trace(trace)

    result = CliRunner().invoke(
        cli, ["replay", trace.trace_id, "--set", "tool.args={}", "--db", str(db_path)]
    )
    assert result.exit_code != 0

    result = CliRunner().invoke(
        cli,
        ["replay", trace.trace_id, "--set", "tool.args={}", "--allow-unsafe", "--db", str(db_path)],
    )
    assert result.exit_code == 0


def test_replay_missing_trace_errors(tmp_path):
    db_path = tmp_path / "t.db"
    SQLiteTraceStore(db_path)

    result = CliRunner().invoke(cli, ["replay", "nonexistent", "--db", str(db_path)])

    assert result.exit_code != 0


def test_test_command_passes(tmp_path):
    db_path = tmp_path / "t.db"
    store = SQLiteTraceStore(db_path)
    trace = Trace(name="checkout", status=SpanStatus.OK)
    store.save_trace(trace)

    tests_dir = tmp_path / "tests"
    tests_dir.mkdir()
    save_test_case(
        TestCase(
            name="checkout succeeds",
            trace_id=trace.trace_id,
            assertions=[Assertion(type=AssertionType.STATUS_OK)],
        ),
        tests_dir / "checkout.json",
    )

    result = CliRunner().invoke(cli, ["test", str(tests_dir), "--db", str(db_path)])

    assert result.exit_code == 0
    assert "PASS" in result.output
    assert "all passed" in result.output


def test_test_command_fails_on_failed_assertion(tmp_path):
    db_path = tmp_path / "t.db"
    store = SQLiteTraceStore(db_path)
    trace = Trace(name="checkout", status=SpanStatus.ERROR)
    store.save_trace(trace)

    tests_dir = tmp_path / "tests"
    tests_dir.mkdir()
    save_test_case(
        TestCase(
            name="checkout succeeds",
            trace_id=trace.trace_id,
            assertions=[Assertion(type=AssertionType.STATUS_OK)],
        ),
        tests_dir / "checkout.json",
    )

    result = CliRunner().invoke(cli, ["test", str(tests_dir), "--db", str(db_path)])

    assert result.exit_code != 0
    assert "FAIL" in result.output


def test_test_command_errors_on_missing_trace(tmp_path):
    db_path = tmp_path / "t.db"
    SQLiteTraceStore(db_path)

    tests_dir = tmp_path / "tests"
    tests_dir.mkdir()
    save_test_case(
        TestCase(name="ghost", trace_id="nonexistent", assertions=[]),
        tests_dir / "ghost.json",
    )

    result = CliRunner().invoke(cli, ["test", str(tests_dir), "--db", str(db_path)])

    assert result.exit_code != 0
    assert "ERROR" in result.output


def test_test_command_no_test_cases(tmp_path):
    db_path = tmp_path / "t.db"
    SQLiteTraceStore(db_path)
    tests_dir = tmp_path / "empty"
    tests_dir.mkdir()

    result = CliRunner().invoke(cli, ["test", str(tests_dir), "--db", str(db_path)])

    assert result.exit_code == 0
    assert "No test cases found" in result.output


def test_analyze_explain_flag_prints_grounded_narrative(tmp_path, monkeypatch):
    import json

    db_path = tmp_path / "t.db"
    store = SQLiteTraceStore(db_path)
    trace = Trace(name="req")
    trace.spans.append(
        Span(
            trace_id=trace.trace_id,
            name="retrieval",
            span_type=SpanType.RETRIEVAL,
            attributes={"documents": []},
        )
    )
    store.save_trace(trace)

    from pyagenthound.graph.builder import build_graph
    from pyagenthound.rules.engine import run_rules

    real_finding_id = run_rules(trace, build_graph(trace))[0].finding_id

    class _FakeProvider:
        name = "fake"
        model = "fake-model"

        def __init__(self, model=None):
            pass

        def complete(self, system, user):
            return json.dumps(
                {"narrative": "No documents came back.", "cited_finding_ids": [real_finding_id]}
            )

    monkeypatch.setattr("pyagenthound.cli.commands.analyze.OllamaProvider", _FakeProvider)

    result = CliRunner().invoke(
        cli, ["analyze", trace.trace_id, "--explain", "--db", str(db_path)]
    )

    assert result.exit_code == 0
    assert "LLM Explanation" in result.output
    assert "No documents came back." in result.output


def test_analyze_explain_flag_shows_unavailable_message(tmp_path, monkeypatch):
    from pyagenthound.llm.providers import LLMUnavailableError

    db_path = tmp_path / "t.db"
    store = SQLiteTraceStore(db_path)
    trace = Trace(name="req")
    trace.spans.append(
        Span(
            trace_id=trace.trace_id,
            name="retrieval",
            span_type=SpanType.RETRIEVAL,
            attributes={"documents": []},
        )
    )
    store.save_trace(trace)

    class _UnavailableProvider:
        def __init__(self, model=None):
            pass

        def complete(self, system, user):
            raise LLMUnavailableError("no ollama here")

    monkeypatch.setattr("pyagenthound.cli.commands.analyze.OllamaProvider", _UnavailableProvider)

    result = CliRunner().invoke(
        cli, ["analyze", trace.trace_id, "--explain", "--db", str(db_path)]
    )

    assert result.exit_code == 0
    assert "unavailable" in result.output
