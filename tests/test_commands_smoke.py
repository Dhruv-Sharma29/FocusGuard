"""One real run of every command, plus --help for each.

conftest.isolate keeps all of this off the real config, database, PID file and keyring.
"""

from __future__ import annotations

import os
from unittest.mock import MagicMock, patch

import psutil
import pytest
from typer.testing import CliRunner

from focusguard import config as cfg
from focusguard.main import app

runner = CliRunner()

COMMANDS = [
    [], ["start"], ["stop"], ["stats"], ["report"],
    ["goal"], ["goal", "add"], ["goal", "list"], ["goal", "complete"], ["goal", "drop"],
    ["coach"], ["coach", "nudge"], ["coach", "roast"], ["coach", "help"], ["coach", "mode"],
    ["coach", "enable"], ["coach", "disable"], ["coach", "setup-openai"],
    ["github"], ["github", "setup"], ["github", "summary"], ["github", "repos"],
    ["daemon"], ["daemon", "install"], ["daemon", "uninstall"], ["daemon", "status"],
    ["privacy"], ["privacy", "show"], ["privacy", "blocklist"], ["privacy", "export-key"],
    ["privacy", "uninstall"],
]


def run(*args: str, **kwargs):  # type: ignore[no-untyped-def]
    result = runner.invoke(app, list(args), **kwargs)
    return result


@pytest.mark.parametrize("command", COMMANDS, ids=lambda c: " ".join(c) or "root")
def test_help(command):
    result = run(*command, "--help")
    assert result.exit_code == 0, result.output
    assert "Usage" in result.output


def test_version():
    assert run("--version").exit_code == 0


# ── Tracking and reports ─────────────────────────────────────────────────────


def test_stats_and_reports(sample_activity, sample_goals):
    for args in (["stats"], ["report"], ["report", "-p", "week"], ["report", "-p", "month"]):
        result = run(*args)
        assert result.exit_code == 0, (args, result.output)
    assert run("report", "-p", "year").exit_code == 1
    assert "Procrastination check" in run("report").output


def test_start_foreground_runs_tracker():
    with (
        patch("focusguard.core.tracker.ActivityTracker") as tracker,
        patch("focusguard.platform.window.check_accessibility_permissions", return_value=True),
    ):
        assert run("start", "--allow-plaintext").exit_code == 0
    tracker.return_value.start.assert_called_once_with(daemon_mode=False)


def test_start_detached_launches_process():
    handler = MagicMock(is_installed=MagicMock(return_value=False))
    with (
        patch("focusguard.commands.daemon._get_platform_handler", return_value=handler),
        patch("focusguard.platform.window.check_accessibility_permissions", return_value=True),
        patch("subprocess.Popen") as popen,
    ):
        result = run("start", "-d", "--allow-plaintext")
    assert result.exit_code == 0, result.output
    assert popen.call_args.args[0][-2:] == ["--daemon-mode", "--allow-plaintext"]


def test_stop():
    assert "not running" in run("stop").output.lower()

    cfg.PID_FILE.parent.mkdir(parents=True, exist_ok=True)
    cfg.PID_FILE.write_text("4242")
    # psutil.Process is fully mocked: no real process is ever signalled.
    with (
        patch("focusguard.core.tracker.psutil.pid_exists", return_value=True),
        patch("focusguard.commands.stop.psutil.Process") as process,
    ):
        result = run("stop")
        assert result.exit_code == 0, result.output
        process.assert_called_with(4242)
        process.return_value.terminate.assert_called_once()

        process.side_effect = psutil.NoSuchProcess(4242)
        result = run("stop")
        assert result.exit_code == 0, result.output
        assert not cfg.PID_FILE.exists()  # stale PID file cleaned up

    cfg.PID_FILE.write_text("4242")
    with (
        patch("focusguard.core.tracker.psutil.pid_exists", return_value=True),
        patch("focusguard.commands.stop.psutil.Process", side_effect=psutil.AccessDenied(4242)),
    ):
        assert run("stop").exit_code == 1


# ── Goals ────────────────────────────────────────────────────────────────────


def test_goal_lifecycle():
    assert run("goal", "add", "Write the report").exit_code == 0
    assert run("goal", "add", "Fix CI").exit_code == 0
    assert "Write the report" in run("goal", "list").output
    assert run("goal", "complete", "1").exit_code == 0
    assert run("goal", "drop", "2").exit_code == 0
    assert run("goal", "complete", "99").exit_code == 1
    assert run("goal", "drop", "99").exit_code == 1
    assert "Write the report" in run("goal", "list", "--all").output


# ── Coach ────────────────────────────────────────────────────────────────────


def test_coach_without_ai(sample_activity, sample_goals):
    for args in (["coach", "nudge"], ["coach", "roast"], ["roast"],
                 ["coach", "help"], ["coach", "help", "-b"], ["help-me"]):
        result = run(*args)
        assert result.exit_code == 0, (args, result.output)
    assert run("coach", "mode", "nonsense").exit_code == 1


def test_coach_help_without_goal():
    assert "No active goal" in run("coach", "help").output


def test_coach_with_ai(sample_activity, sample_goals):
    assert run("coach", "enable", "-p", "openai").exit_code == 0
    assert cfg.load_config().ai.provider == "openai"
    with patch("focusguard.integrations.llm.chat", return_value="Ship the smallest slice."):
        assert "smallest slice" in run("coach", "help").output
        assert "smallest slice" in run("coach", "help", "-b").output
    assert run("coach", "disable").exit_code == 0
    assert cfg.load_config().ai.enabled is False


def test_setup_openai_stores_key_in_keyring(isolate):
    result = run("coach", "setup-openai", input="sk-test\n")
    assert result.exit_code == 0, result.output
    assert "sk-test" in isolate.values()


# ── GitHub ───────────────────────────────────────────────────────────────────


def test_github_summary_unconfigured():
    with patch("focusguard.integrations.github_api.is_configured", return_value=False):
        assert run("github", "summary").exit_code == 1


def test_github_setup_stores_token(isolate):
    assert run("github", "setup", input="ghp_test\n").exit_code == 0
    assert "ghp_test" in isolate.values()


def test_github_summary_renders():
    from focusguard.integrations.github_api import GitHubSummary

    result = GitHubSummary(username="me", period_days=7, total_commits=12,
                           most_active_repo="FocusGuard", repos_contributed=["FocusGuard"])
    with (
        patch("focusguard.integrations.github_api.is_configured", return_value=True),
        patch("focusguard.integrations.github_api.get_weekly_summary", return_value=result),
    ):
        out = run("github", "summary")
    assert out.exit_code == 0, out.output
    assert "@me" in out.output
    with (
        patch("focusguard.integrations.github_api.is_configured", return_value=True),
        patch("focusguard.integrations.github_api.get_weekly_summary", return_value=None),
    ):
        assert run("github", "summary").exit_code == 1


def test_github_repos(tmp_path):
    from focusguard.integrations.git_tracker import RepoSummary

    assert "No git repos" in run("github", "repos", str(tmp_path)).output
    (tmp_path / "proj" / ".git").mkdir(parents=True)  # found by directory walk, no git needed
    summary = RepoSummary("proj", str(tmp_path / "proj"), 2, 5, [], 40, 3, True)
    with patch("focusguard.integrations.git_tracker.scan_all_repos", return_value=[summary]):
        out = run("github", "repos", str(tmp_path))
    assert out.exit_code == 0, out.output
    assert "proj" in out.output


# ── Daemon ───────────────────────────────────────────────────────────────────


def test_daemon_commands():
    handler = MagicMock()
    with patch("focusguard.commands.daemon._get_platform_handler", return_value=handler):
        assert run("daemon", "install", "--allow-plaintext").exit_code == 0
        handler.install.assert_called_with(["--allow-plaintext"])
        assert run("daemon", "uninstall").exit_code == 0
        handler.install.side_effect = OSError("denied")
        assert run("daemon", "install", "--allow-plaintext").exit_code == 1
    assert "not running" in run("daemon", "status").output.lower()


# ── Privacy ──────────────────────────────────────────────────────────────────


def test_privacy_show_and_list():
    result = run("privacy", "show")
    assert result.exit_code == 0
    assert "What IS Tracked" in result.output
    assert "patterns" in run("privacy", "blocklist").output
    assert run("privacy", "blocklist", "frobnicate").exit_code == 1


def test_export_key(isolate):
    assert "No encryption key" in run("privacy", "export-key").output
    isolate[("focusguard", "db_encryption_key")] = "ab" * 32
    assert "ab" * 32 in run("privacy", "export-key").output


def test_uninstall_removes_only_temp_paths(isolate):
    for d in (cfg.CONFIG_DIR, cfg.DATA_DIR, cfg.LOG_DIR):
        d.mkdir(parents=True, exist_ok=True)
    isolate[("focusguard", "github_token")] = "ghp_test"
    assert "fg" in cfg.DATA_DIR.parts  # the fixture's temp tree, never the real one

    assert run("privacy", "uninstall", input="n\n").exit_code == 0
    assert cfg.DATA_DIR.exists()  # declined

    with patch("focusguard.commands.daemon._get_platform_handler", return_value=MagicMock()):
        result = run("privacy", "uninstall", "-y")
    assert result.exit_code == 0, result.output
    assert not any(d.exists() for d in (cfg.CONFIG_DIR, cfg.DATA_DIR, cfg.LOG_DIR))
    assert ("focusguard", "github_token") not in isolate


def test_no_real_paths_touched():
    home = os.path.expanduser("~")
    for p in (cfg.CONFIG_FILE, cfg.DB_FILE, cfg.PID_FILE):
        assert not str(p).startswith(os.path.join(home, "Library"))
        assert not str(p).startswith(os.path.join(home, ".config"))


# ── Encryption gate (--allow-plaintext) ──────────────────────────────────────


@pytest.fixture
def no_sqlcipher(monkeypatch):
    from focusguard.db import connection

    monkeypatch.setattr(connection, "HAS_SQLCIPHER", False)


def test_start_refuses_plaintext_without_flag(no_sqlcipher):
    with patch("focusguard.core.tracker.ActivityTracker") as tracker:
        result = run("start")
    assert result.exit_code == 1
    assert "--allow-plaintext" in result.output
    tracker.assert_not_called()


def test_service_launched_tracker_refuses_with_exit_0(no_sqlcipher):
    """Exit 0, or launchd/systemd would restart it every 10 s."""
    with patch("focusguard.core.tracker.ActivityTracker") as tracker:
        assert run("start", "--daemon-mode").exit_code == 0
    tracker.assert_not_called()


def test_daemon_install_refuses_plaintext_without_flag(no_sqlcipher):
    handler = MagicMock()
    with patch("focusguard.commands.daemon._get_platform_handler", return_value=handler):
        assert run("daemon", "install").exit_code == 1
    handler.install.assert_not_called()


def test_plain_file_with_sqlcipher_points_to_encrypt(monkeypatch):
    from focusguard.db import connection

    monkeypatch.setattr(connection, "HAS_SQLCIPHER", True)
    monkeypatch.setattr(connection, "is_plaintext_db", lambda path=None: True)
    result = run("start")
    assert result.exit_code == 1
    assert "privacy encrypt" in result.output


def test_service_files_carry_the_flag(tmp_path, monkeypatch):
    """The installed launchd plist / systemd unit really contain --allow-plaintext."""
    import subprocess

    from focusguard.platform import daemon_linux, daemon_macos

    monkeypatch.setattr(subprocess, "run", MagicMock())
    monkeypatch.setattr(daemon_macos, "LAUNCH_AGENTS_DIR", tmp_path)
    monkeypatch.setattr(daemon_macos, "PLIST_PATH", tmp_path / "x.plist")
    monkeypatch.setattr(daemon_linux, "SYSTEMD_USER_DIR", tmp_path)
    monkeypatch.setattr(daemon_linux, "SERVICE_PATH", tmp_path / "x.service")
    daemon_macos.MacOSDaemon().install(["--allow-plaintext"])
    daemon_linux.LinuxDaemon().install(["--allow-plaintext"])
    import plistlib

    plist = plistlib.loads((tmp_path / "x.plist").read_bytes())  # must stay valid XML
    assert plist["ProgramArguments"][-2:] == ["--daemon-mode", "--allow-plaintext"]
    assert "--daemon-mode --allow-plaintext" in (tmp_path / "x.service").read_text()
