"""Schema migrations and SQLCipher handling (docs/05-known-issues.md #10)."""

from __future__ import annotations

import sqlite3
from datetime import datetime

import pytest
from typer.testing import CliRunner

from focusguard import config as cfg
from focusguard.db import connection, models, queries
from focusguard.main import app

runner = CliRunner()
NEXT_STEP = "CREATE TABLE future_table (x INTEGER);"
CURRENT = models.SCHEMA_VERSION


def _tables() -> set[str]:
    rows = connection.query("SELECT name FROM sqlite_master WHERE type = 'table'")
    return {r["name"] for r in rows}


# ── Migrations ───────────────────────────────────────────────────────────────


def test_fresh_db_is_at_current_version():
    assert models.get_schema_version() == CURRENT == len(models.MIGRATIONS)
    assert "ratings" in _tables()  # v2


def test_v1_database_upgrades_with_data_intact(tmp_path, monkeypatch):
    """A database written by v0.1.0 (schema v1) gains the v2 ratings table and keeps its rows."""
    path = tmp_path / "v1.db"
    _plain_db(path, rows=4)
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    monkeypatch.setattr(connection, "_get_connection", lambda: conn)
    models.init_db()
    assert models.get_schema_version() == CURRENT
    assert "ratings" in _tables()
    assert connection.query("SELECT COUNT(*) AS n FROM activity_log")[0]["n"] == 4
    conn.close()


def test_new_step_upgrades_and_keeps_data(monkeypatch):
    queries.log_activity("Code", "a.py", "coding", 60, False)
    monkeypatch.setattr(models, "MIGRATIONS", [*models.MIGRATIONS, NEXT_STEP])
    models.init_db()
    models.init_db()  # idempotent
    assert models.get_schema_version() == CURRENT + 1
    assert "future_table" in _tables()
    assert len(queries.get_activity_range(datetime(2000, 1, 1))) == 1


def test_failed_step_rolls_back(monkeypatch):
    broken = "CREATE TABLE half_done (x INTEGER); INSERT INTO no_such_table VALUES (1);"
    monkeypatch.setattr(models, "MIGRATIONS", [*models.MIGRATIONS, broken])
    with pytest.raises(sqlite3.OperationalError):
        models.init_db()
    assert models.get_schema_version() == CURRENT
    assert "half_done" not in _tables()


def test_newer_database_is_refused():
    connection.execute("INSERT INTO schema_version (version) VALUES (99)")
    with pytest.raises(RuntimeError, match="newer"):
        models.init_db()


# ── Plaintext detection ─────────────────────────────────────────────────────


def _plain_db(path, rows: int = 3) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    conn.executescript(models.SCHEMA_V1 + "INSERT INTO schema_version VALUES (1);")
    for i in range(rows):
        conn.execute(
            "INSERT INTO activity_log (app_name, category) VALUES (?, 'coding')", (f"app{i}",)
        )
    conn.commit()
    conn.close()


def test_is_plaintext_db(tmp_path):
    assert not connection.is_plaintext_db(tmp_path / "missing.db")
    _plain_db(tmp_path / "plain.db")
    assert connection.is_plaintext_db(tmp_path / "plain.db")
    (tmp_path / "noise.db").write_bytes(b"\x8f" * 64)  # what an encrypted file looks like
    assert not connection.is_plaintext_db(tmp_path / "noise.db")


def test_plain_db_opens_unencrypted_even_with_sqlcipher(monkeypatch):
    """v0.1.0 keyed this file and every query failed with 'file is not a database'."""
    _plain_db(cfg.DB_FILE)
    monkeypatch.setattr(connection, "HAS_SQLCIPHER", True)
    monkeypatch.setattr(connection, "sqlcipher", None, raising=False)  # must not be used
    conn = connection._open(str(cfg.DB_FILE))
    assert conn.execute("SELECT COUNT(*) FROM activity_log").fetchone()[0] == 3
    conn.close()

    result = runner.invoke(app, ["privacy", "show"])
    assert "NOT encrypted" in result.output


def test_encrypt_needs_sqlcipher(monkeypatch):
    monkeypatch.setattr(connection, "HAS_SQLCIPHER", False)
    assert runner.invoke(app, ["privacy", "encrypt"]).exit_code == 1


def test_encrypt_round_trip(isolate):
    """Runs against the real library (CI 'encrypted' job; sqlcipher3 has Linux wheels only)."""
    pytest.importorskip("sqlcipher3")
    from sqlcipher3 import dbapi2 as sqlcipher

    _plain_db(cfg.DB_FILE, rows=5)
    result = runner.invoke(app, ["privacy", "encrypt"])
    assert result.exit_code == 0, result.output
    assert not connection.is_plaintext_db()

    key = isolate[("focusguard", "db_encryption_key")]
    conn = sqlcipher.connect(str(cfg.DB_FILE))
    conn.execute(f"PRAGMA key = '{key}'")
    assert conn.execute("SELECT COUNT(*) FROM activity_log").fetchone()[0] == 5
    conn.close()

    wrong = sqlcipher.connect(str(cfg.DB_FILE))
    wrong.execute("PRAGMA key = 'not-the-key'")
    with pytest.raises(sqlcipher.DatabaseError):
        wrong.execute("SELECT COUNT(*) FROM activity_log").fetchone()
    wrong.close()

    assert "Nothing to do" in runner.invoke(app, ["privacy", "encrypt"]).output
