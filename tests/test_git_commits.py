"""Phase 6: commits from [github] tracked_repos, read with the git binary."""

from __future__ import annotations

import os
import shutil
import subprocess
from datetime import datetime, timedelta
from unittest.mock import patch

import pytest
from typer.testing import CliRunner

from focusguard.config import FocusGuardConfig
from focusguard.core.tracker import ActivityTracker
from focusguard.db import queries
from focusguard.integrations.git_tracker import own_commits_since
from focusguard.main import app
from focusguard.platform.window import WindowInfo

pytestmark = pytest.mark.skipif(shutil.which("git") is None, reason="needs git")

ME, THEM = "me@example.com", "them@example.com"


@pytest.fixture
def repo(tmp_path, monkeypatch):
    """A repo with 2 commits by ME (3 and 1 days ago) and 1 by THEM, on two branches."""
    empty = tmp_path / "empty.gitconfig"
    empty.write_text("")
    monkeypatch.setenv("GIT_CONFIG_GLOBAL", str(empty))  # ignore the real user's config
    monkeypatch.setenv("GIT_CONFIG_NOSYSTEM", "1")
    path = tmp_path / "proj"
    path.mkdir()

    def git(*args: str, env: dict[str, str] | None = None) -> None:
        subprocess.run(["git", "-C", str(path), *args], check=True, capture_output=True,
                       env={**os.environ, **(env or {})})

    def commit(msg: str, email: str, days_ago: int) -> None:
        when = (datetime.now() - timedelta(days=days_ago)).strftime("%Y-%m-%dT%H:%M:%S")
        git("commit", "--allow-empty", "-m", msg,
            env={"GIT_AUTHOR_NAME": "x", "GIT_AUTHOR_EMAIL": email, "GIT_AUTHOR_DATE": when,
                 "GIT_COMMITTER_NAME": "x", "GIT_COMMITTER_EMAIL": email,
                 "GIT_COMMITTER_DATE": when})

    git("init", "-q", "-b", "main")
    git("config", "user.email", ME)
    commit("old", ME, 30)
    commit("mine 1", ME, 3)
    commit("theirs", THEM, 2)
    git("checkout", "-q", "-b", "feature")
    commit("mine 2", ME, 1)  # only on a branch: --all must find it
    git("checkout", "-q", "main")
    return path


def test_own_commits_since(repo):
    commits = own_commits_since(str(repo), datetime.now() - timedelta(days=7))
    assert len(commits) == 2  # not THEM's, not the 30-day-old one
    assert commits[0][1] < commits[1][1]  # oldest first
    assert (datetime.now() - commits[1][1]).days == 1


def test_not_a_repo_returns_empty(tmp_path):
    assert own_commits_since(str(tmp_path), datetime.now() - timedelta(days=7)) == []


def test_tracker_logs_commits_once_with_commit_times(repo):
    config = FocusGuardConfig()
    config.github.tracked_repos = [str(repo)]
    with patch("focusguard.core.tracker.load_config", return_value=config):
        tracker = ActivityTracker()
    with (
        patch("focusguard.core.tracker.get_active_window", return_value=WindowInfo("Code", "a")),
        patch("focusguard.core.tracker.get_idle_seconds", return_value=0),
        patch("focusguard.core.tracker.run_retention_policy", return_value={}),
    ):
        tracker._poll_tick()
        tracker._poll_tick()                       # within the hour: no rescan
        tracker._last_commit_scan -= timedelta(hours=2)
        tracker._poll_tick()                       # rescans; SHAs already logged
    week = queries.get_commit_count(datetime.now() - timedelta(days=7), datetime.now())
    assert week == 2
    yesterday = datetime.now() - timedelta(days=1)
    day = queries.get_commit_count(
        yesterday.replace(hour=0, minute=0, second=0), yesterday.replace(hour=23, minute=59)
    )
    assert day == 1  # counted on the day it was committed, not the day it was scanned

    result = CliRunner().invoke(app, ["report", "-p", "week"])
    assert result.exit_code == 0
