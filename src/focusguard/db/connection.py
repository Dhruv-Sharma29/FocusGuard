"""Encrypted SQLite database connection manager.

Uses sqlcipher3 for transparent AES-256 encryption at rest.
The encryption key is stored in the OS keyring (never on disk).
Falls back to standard sqlite3 if sqlcipher3 is not available
(with a warning — unencrypted mode is for development only).
"""

from __future__ import annotations

import contextlib
import os
import sqlite3
import threading
from collections.abc import Generator
from pathlib import Path
from typing import Any

from rich.console import Console

from focusguard.config import DB_FILE, ensure_dirs
from focusguard.security.crypto import get_or_create_db_key

console = Console(stderr=True)

# Try to use sqlcipher for encrypted database
try:
    from sqlcipher3 import dbapi2 as sqlcipher

    HAS_SQLCIPHER = True
except ImportError:
    HAS_SQLCIPHER = False

# Thread-local storage for connections (one connection per thread)
_local = threading.local()
_warned_plaintext = False


SQLITE_HEADER = b"SQLite format 3\x00"


def is_plaintext_db(path: Path | None = None) -> bool:
    """True if the database file exists and is plain (unencrypted) SQLite."""
    try:
        with open(path or DB_FILE, "rb") as f:
            return f.read(16) == SQLITE_HEADER
    except FileNotFoundError:
        return False


def is_encrypted() -> bool:
    """True when the database is (or, once created, will be) opened with SQLCipher."""
    return HAS_SQLCIPHER and not is_plaintext_db()


def _open(db_path: str) -> sqlite3.Connection:
    """Open the database: SQLCipher when available, unless the file is plain SQLite."""
    global _warned_plaintext
    conn: sqlite3.Connection
    if is_encrypted():
        conn = sqlcipher.connect(db_path)
        key = get_or_create_db_key()
        conn.execute(f"PRAGMA key = '{key}';")
    else:
        # Once per process, and not into the daemon's log file.
        if not _warned_plaintext and console.is_terminal:
            if HAS_SQLCIPHER:
                console.print(
                    "[yellow]⚠ This database was created without encryption "
                    "and is NOT encrypted.[/yellow]"
                )
                console.print("[dim]Encrypt it with: focusguard privacy encrypt[/dim]")
            else:
                console.print(
                    "[yellow]⚠ sqlcipher3 not installed — database is NOT encrypted.[/yellow]"
                )
                console.print("[dim]Install with: pip install sqlcipher3-binary[/dim]")
        _warned_plaintext = True
        conn = sqlite3.connect(db_path)

    # Enable WAL mode for concurrent reads during report generation
    conn.execute("PRAGMA journal_mode = WAL;")
    conn.execute("PRAGMA foreign_keys = ON;")
    # Return rows as sqlite3.Row for dict-like access
    conn.row_factory = sqlite3.Row
    return conn


def _get_connection() -> sqlite3.Connection:
    """Get or create a database connection for the current thread."""
    if hasattr(_local, "connection") and _local.connection is not None:
        return _local.connection  # type: ignore[no-any-return]
    ensure_dirs()
    _local.connection = _open(str(DB_FILE))
    return _local.connection  # type: ignore[no-any-return]


def _row_counts(conn: Any) -> dict[str, int]:
    tables = [
        r[0]
        for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type = 'table' AND name NOT LIKE 'sqlite_%'"
        )
    ]
    return {t: conn.execute(f'SELECT COUNT(*) FROM "{t}"').fetchone()[0] for t in tables}


def encrypt_plaintext_db() -> int:
    """Encrypt the existing plain database in place. Returns the number of rows copied.

    Copies into a new SQLCipher file with sqlcipher_export, checks every table's row
    count, and only then replaces the original. On any failure the original is kept.
    The caller must make sure no tracker has the file open.
    """
    if not HAS_SQLCIPHER:
        raise RuntimeError("sqlcipher3 is not installed")
    src = Path(DB_FILE)
    if not is_plaintext_db(src):
        raise RuntimeError(f"No unencrypted database at {src}")
    close()
    tmp = src.with_name(src.name + ".encrypting")
    tmp.unlink(missing_ok=True)
    key = get_or_create_db_key()  # 64 hex chars, safe to inline below

    plain = sqlcipher.connect(str(src))  # no key: reads plain SQLite
    try:
        plain.execute("PRAGMA wal_checkpoint(TRUNCATE)")
        counts = _row_counts(plain)
        plain.execute(f"ATTACH DATABASE ? AS encrypted KEY '{key}'", (str(tmp),))
        plain.execute("SELECT sqlcipher_export('encrypted')")
        plain.execute("DETACH DATABASE encrypted")
    finally:
        plain.close()

    enc = sqlcipher.connect(str(tmp))
    try:
        enc.execute(f"PRAGMA key = '{key}'")
        copied = _row_counts(enc)
    finally:
        enc.close()
    if copied != counts:
        tmp.unlink(missing_ok=True)
        raise RuntimeError(f"Verification failed ({counts} vs {copied}); original kept.")

    for suffix in ("-wal", "-shm"):
        Path(f"{src}{suffix}").unlink(missing_ok=True)
    os.replace(tmp, src)
    return sum(counts.values())


@contextlib.contextmanager
def get_db() -> Generator[sqlite3.Connection, None, None]:
    """Context manager for database access.

    Yields:
        An active database connection. Auto-commits on success,
        rolls back on exception.

    Usage:
        with get_db() as db:
            db.execute("INSERT INTO ...")
    """
    conn = _get_connection()
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise


def execute(sql: str, params: tuple[Any, ...] = ()) -> sqlite3.Cursor:
    """Execute a SQL statement and commit.

    Args:
        sql: SQL string (use ? placeholders for params).
        params: Tuple of parameters for the query.

    Returns:
        The cursor after execution.
    """
    conn = _get_connection()
    cursor = conn.execute(sql, params)
    conn.commit()
    return cursor


def query(sql: str, params: tuple[Any, ...] = ()) -> list[sqlite3.Row]:
    """Execute a SELECT query and return all rows.

    Args:
        sql: SQL SELECT string.
        params: Tuple of parameters.

    Returns:
        List of sqlite3.Row objects (dict-like access).
    """
    conn = _get_connection()
    return conn.execute(sql, params).fetchall()


def query_one(sql: str, params: tuple[Any, ...] = ()) -> sqlite3.Row | None:
    """Execute a SELECT query and return the first row.

    Args:
        sql: SQL SELECT string.
        params: Tuple of parameters.

    Returns:
        A single sqlite3.Row, or None if no results.
    """
    row: sqlite3.Row | None = _get_connection().execute(sql, params).fetchone()
    return row


def close() -> None:
    """Close the database connection for the current thread."""
    if hasattr(_local, "connection") and _local.connection is not None:
        _local.connection.close()
        _local.connection = None
