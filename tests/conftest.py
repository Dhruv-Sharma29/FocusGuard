"""Shared fixtures for FocusGuard tests.

Uses an in-memory unencrypted SQLite database for all tests
to avoid touching the real database or requiring sqlcipher.
"""

from __future__ import annotations

import sqlite3
import threading
from unittest.mock import patch

import pytest

_PATH_NAMES = ("CONFIG_DIR", "CONFIG_FILE", "DATA_DIR", "LOG_DIR", "DB_FILE", "PID_FILE")


@pytest.fixture(autouse=True)
def isolate(tmp_path, monkeypatch):
    """Keep every test off the real config, data, PID file and OS keyring.

    Paths are patched in every loaded focusguard module (they are imported by name),
    which also works on Windows, where platformdirs ignores HOME.
    """
    import sys

    import keyring

    import focusguard.core.tracker
    import focusguard.main  # noqa: F401  (loads every command module before patching)
    from focusguard import config

    home = tmp_path / "fg"
    paths = {
        "CONFIG_DIR": home / "config",
        "DATA_DIR": home / "data",
        "LOG_DIR": home / "log",
    }
    paths["CONFIG_FILE"] = paths["CONFIG_DIR"] / "config.toml"
    paths["DB_FILE"] = paths["DATA_DIR"] / "focus.db"
    paths["PID_FILE"] = paths["DATA_DIR"] / "focusguard.pid"
    assert set(paths) == set(_PATH_NAMES)
    modules = [m for name, m in list(sys.modules.items()) if name.startswith("focusguard")]
    for module in [config, *modules]:
        for name, value in paths.items():
            if hasattr(module, name):
                monkeypatch.setattr(module, name, value)

    secrets: dict[tuple[str, str], str] = {}
    monkeypatch.setattr(keyring, "get_password", lambda s, n: secrets.get((s, n)))
    monkeypatch.setattr(keyring, "set_password", lambda s, n, v: secrets.__setitem__((s, n), v))

    def delete_password(s: str, n: str) -> None:
        from keyring.errors import PasswordDeleteError

        if (s, n) not in secrets:
            raise PasswordDeleteError(n)
        del secrets[(s, n)]

    monkeypatch.setattr(keyring, "delete_password", delete_password)
    return secrets


@pytest.fixture(autouse=True)
def mock_db(tmp_path, isolate):
    """Replace the database with a temporary unencrypted SQLite file.

    This fixture patches the connection module so tests never touch
    the real database or require sqlcipher.
    """
    db_path = tmp_path / "test_focus.db"
    _local = threading.local()

    def _get_test_connection() -> sqlite3.Connection:
        if hasattr(_local, "connection") and _local.connection is not None:
            return _local.connection
        conn = sqlite3.connect(str(db_path))
        conn.execute("PRAGMA journal_mode = WAL;")
        conn.execute("PRAGMA foreign_keys = ON;")
        conn.row_factory = sqlite3.Row
        _local.connection = conn
        return conn

    with patch("focusguard.db.connection._get_connection", _get_test_connection):
        # Initialize schema
        from focusguard.db.models import init_db
        init_db()
        yield db_path

    # Cleanup
    if hasattr(_local, "connection") and _local.connection:
        _local.connection.close()


@pytest.fixture
def sample_activity(mock_db):
    """Insert sample activity data for testing."""
    from focusguard.db.queries import log_activity

    entries = [
        ("VS Code", "main.py — project", "coding", 60, False),
        ("VS Code", "utils.py — project", "coding", 60, False),
        ("VS Code", "test_main.py — project", "coding", 60, False),
        ("Chrome", "Stack Overflow", "browser", 60, False),
        ("Chrome", "YouTube - Music", "entertainment", 60, False),
        ("Chrome", "YouTube - Tutorial", "entertainment", 60, False),
        ("Slack", "team-general", "communication", 60, False),
        ("Terminal", "zsh", "coding", 60, False),
        ("Unknown", None, "other", 60, True),  # idle
    ]

    ids = []
    for app, title, cat, dur, idle in entries:
        row_id = log_activity(app, title, cat, dur, idle)
        ids.append(row_id)

    return ids


@pytest.fixture
def sample_goals(mock_db):
    """Insert sample goals for testing."""
    from focusguard.db.queries import add_goal

    g1 = add_goal("Build authentication system")
    g2 = add_goal("Write unit tests")
    return [g1, g2]
