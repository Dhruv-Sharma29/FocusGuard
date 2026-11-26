"""CLI tests: run real commands against a temp config file."""

from __future__ import annotations

import pytest
from typer.testing import CliRunner

from focusguard import config as cfg
from focusguard.main import app

runner = CliRunner()


@pytest.fixture
def config_file(tmp_path, monkeypatch):
    monkeypatch.setattr(cfg, "CONFIG_DIR", tmp_path)
    monkeypatch.setattr(cfg, "CONFIG_FILE", tmp_path / "config.toml")
    return tmp_path / "config.toml"


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
