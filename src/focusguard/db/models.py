"""Database schema definitions and migrations for FocusGuard.

All table creation and schema upgrades happen here.
Uses a simple version-based migration strategy.
"""

from __future__ import annotations

from focusguard.db import connection
from focusguard.db.connection import execute, query_one

# ── Schema SQL ───────────────────────────────────────────────────────────────

SCHEMA_V1 = """
-- Activity log: one row per poll tick (every 60 seconds)
CREATE TABLE IF NOT EXISTS activity_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp DATETIME NOT NULL DEFAULT (datetime('now', 'localtime')),
    app_name TEXT NOT NULL,
    window_title TEXT,
    category TEXT NOT NULL,
    duration_seconds INTEGER NOT NULL DEFAULT 60,
    is_idle BOOLEAN NOT NULL DEFAULT 0
);

-- Focus scores: periodic snapshots of productivity metrics
CREATE TABLE IF NOT EXISTS focus_scores (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp DATETIME NOT NULL DEFAULT (datetime('now', 'localtime')),
    score REAL NOT NULL,
    coding_minutes REAL NOT NULL DEFAULT 0,
    distraction_minutes REAL NOT NULL DEFAULT 0,
    total_minutes REAL NOT NULL DEFAULT 0,
    period TEXT NOT NULL
);

-- Goals: user-defined tasks to work on
CREATE TABLE IF NOT EXISTS goals (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    description TEXT NOT NULL,
    created_at DATETIME NOT NULL DEFAULT (datetime('now', 'localtime')),
    completed_at DATETIME,
    is_active BOOLEAN NOT NULL DEFAULT 1
);

-- Git activity: commits, PRs, issues from local repos + GitHub
CREATE TABLE IF NOT EXISTS git_activity (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp DATETIME NOT NULL DEFAULT (datetime('now', 'localtime')),
    repo_name TEXT,
    event_type TEXT NOT NULL,
    details TEXT
);

-- Daily summaries: aggregated data for retention policy
CREATE TABLE IF NOT EXISTS daily_summaries (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    date DATE NOT NULL UNIQUE,
    total_minutes REAL NOT NULL DEFAULT 0,
    coding_minutes REAL NOT NULL DEFAULT 0,
    distraction_minutes REAL NOT NULL DEFAULT 0,
    avg_focus_score REAL,
    top_apps TEXT,
    git_commits INTEGER NOT NULL DEFAULT 0
);

-- Schema version tracking
CREATE TABLE IF NOT EXISTS schema_version (
    version INTEGER PRIMARY KEY
);

-- Indices for fast queries
CREATE INDEX IF NOT EXISTS idx_activity_timestamp ON activity_log(timestamp);
CREATE INDEX IF NOT EXISTS idx_activity_category ON activity_log(category);
CREATE INDEX IF NOT EXISTS idx_scores_timestamp ON focus_scores(timestamp);
CREATE INDEX IF NOT EXISTS idx_scores_period ON focus_scores(period);
CREATE INDEX IF NOT EXISTS idx_goals_active ON goals(is_active);
CREATE INDEX IF NOT EXISTS idx_git_timestamp ON git_activity(timestamp);
CREATE INDEX IF NOT EXISTS idx_daily_date ON daily_summaries(date);
"""


# MIGRATIONS[i] upgrades a database from version i to version i + 1.
# Append new steps; never edit one that has shipped.
MIGRATIONS: list[str] = [SCHEMA_V1]
SCHEMA_VERSION = len(MIGRATIONS)


def init_db() -> None:
    """Create the schema or upgrade it to SCHEMA_VERSION. Safe to call repeatedly.

    Each step runs in one transaction together with its version bump, so a failed
    step leaves the database as it was.
    """
    execute("CREATE TABLE IF NOT EXISTS schema_version (version INTEGER PRIMARY KEY)")
    current = get_schema_version()
    if current > len(MIGRATIONS):
        raise RuntimeError(
            f"The database is at schema v{current}, newer than this FocusGuard "
            f"supports (v{len(MIGRATIONS)}). Upgrade FocusGuard."
        )
    conn = connection._get_connection()
    for version in range(current + 1, len(MIGRATIONS) + 1):
        try:
            conn.executescript(
                f"BEGIN;\n{MIGRATIONS[version - 1]}\n"
                f"INSERT INTO schema_version (version) VALUES ({version});\nCOMMIT;"
            )
        except Exception:
            conn.rollback()
            raise


def get_schema_version() -> int:
    """Get the current schema version.

    Returns:
        The version number, or 0 if the schema hasn't been initialized.
    """
    try:
        row = query_one("SELECT version FROM schema_version ORDER BY version DESC LIMIT 1")
        return int(row["version"]) if row else 0
    except Exception:
        return 0
