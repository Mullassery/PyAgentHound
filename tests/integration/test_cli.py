from click.testing import CliRunner

from pyagenthound.cli.main import cli
from pyagenthound.sdk.models import Trace
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
