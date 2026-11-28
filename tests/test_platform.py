"""Real OS calls, no mocks: the claims docs/ marked [verify], checked on each CI runner."""

from __future__ import annotations

import os
import shutil
import sys
from pathlib import Path

import pytest
from platformdirs import user_config_dir, user_data_dir

from focusguard.platform import idle


@pytest.mark.skipif(sys.platform != "win32", reason="Windows only")
def test_windows_idle_reads_last_input():
    seconds = idle._idle_windows()  # direct call, so a failure shows the real error
    assert seconds >= 0


@pytest.mark.skipif(
    not (sys.platform == "linux" and os.environ.get("DISPLAY") and shutil.which("xprintidle")),
    reason="needs X11 and xprintidle (CI 'encrypted' job runs under xvfb)",
)
def test_x11_idle_reads_xprintidle():
    seconds = idle._idle_x11()
    assert seconds is not None and seconds >= 0


@pytest.mark.skipif(sys.platform != "darwin", reason="macOS only")
def test_macos_idle_reads_ioreg():
    seconds = idle._idle_macos()
    assert seconds is not None and seconds >= 0


@pytest.mark.skipif(sys.platform != "win32", reason="Windows only")
def test_windows_paths_match_start_md():
    """start.md § 8 says %LOCALAPPDATA%\\focusguard\\focusguard for config and data."""
    local = Path(os.environ["LOCALAPPDATA"])
    assert Path(user_config_dir("focusguard")) == local / "focusguard" / "focusguard"
    assert Path(user_data_dir("focusguard")) == local / "focusguard" / "focusguard"
