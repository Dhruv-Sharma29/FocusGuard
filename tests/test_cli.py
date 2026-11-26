"""CLI tests: run real commands against a temp config file."""

from __future__ import annotations

import pytest
from typer.testing import CliRunner

from focusguard import config as cfg
from focusguard.main import app

runner = CliRunner()


@pytest.fixture
def config_file():
    return cfg.CONFIG_FILE  # already a temp path (conftest.isolate)


def test_blocklist_add_and_remove_persist(config_file):
    assert runner.invoke(app, ["privacy", "blocklist", "add", "mybank"]).exit_code == 0
    assert "mybank" in cfg.load_config().security.blocklist

    assert runner.invoke(app, ["privacy", "blocklist", "remove", "mybank"]).exit_code == 0
    assert "mybank" not in cfg.load_config().security.blocklist


def test_blocklist_remove_missing_fails(config_file):
    assert runner.invoke(app, ["privacy", "blocklist", "remove", "nope"]).exit_code == 1


def test_coach_mode_persists(config_file):
    assert runner.invoke(app, ["coach", "mode", "roast"]).exit_code == 0
    assert cfg.load_config().personality.mode == "roast"


def test_config_round_trips_backslash_and_quote(config_file):
    """v0.1.0's hand-written TOML writer produced an unreadable file here."""
    config = cfg.load_config()
    config.github.tracked_repos = [r"C:\Users\me\repo", 'say "hi"']
    cfg.save_config(config)
    assert runner.invoke(app, ["coach", "enable"]).exit_code == 0  # rewrites the file
    with open(config_file, "rb") as f:
        cfg.tomllib.load(f)  # must parse
    assert cfg.load_config().github.tracked_repos == [r"C:\Users\me\repo", 'say "hi"']


def test_coach_help_falls_back_when_llm_fails(config_file, sample_goals):
    from unittest.mock import patch

    config = cfg.load_config()
    config.ai.enabled = True
    cfg.save_config(config)
    with patch("focusguard.integrations.llm.chat", side_effect=RuntimeError("no server")):
        result = runner.invoke(app, ["coach", "help"])
    assert result.exit_code == 0
    assert "AI error: no server" in result.output
    assert "Build authentication system" in result.output  # the local summary really prints


def test_start_daemon_refuses_when_service_installed(config_file):
    from unittest.mock import MagicMock, patch

    handler = MagicMock(is_installed=MagicMock(return_value=True))
    with (
        patch("focusguard.core.tracker.is_tracker_running", return_value=False),
        patch("focusguard.commands.daemon._get_platform_handler", return_value=handler),
        patch("focusguard.commands.start._launch_daemon") as launch,
    ):
        result = runner.invoke(app, ["start", "-d"])
    assert result.exit_code == 1
    launch.assert_not_called()


def test_service_launch_exits_cleanly_when_tracker_running(config_file):
    """Exit 0, so launchd/systemd don't restart it every 10 s."""
    from unittest.mock import patch

    with patch("focusguard.core.tracker.is_tracker_running", return_value=True):
        assert runner.invoke(app, ["start", "--daemon-mode"]).exit_code == 0
