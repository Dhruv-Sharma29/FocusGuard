"""Activity tracker — the core polling loop.

Every poll_interval seconds (default 60), this module:
1. Gets the active window (app name + title)
2. Sanitizes the title through the blocklist filter
3. Classifies the app into a category
4. Logs the activity to the database
5. Recalculates the running focus score

The tracker runs in its own thread and can be cleanly stopped
via a threading.Event signal.
"""

from __future__ import annotations

import logging
import os
import re
import signal
import sys
import threading
import time
from datetime import date, datetime, timedelta

import psutil
from rich.console import Console

from focusguard.config import DATA_DIR, PID_FILE, load_config
from focusguard.core.retention import run_retention_policy
from focusguard.core.scorer import snapshot_score
from focusguard.db.models import init_db
from focusguard.db.queries import log_activity
from focusguard.platform.idle import get_idle_seconds
from focusguard.platform.window import WindowInfo, get_active_window
from focusguard.security.blocklist import sanitize_title

logger = logging.getLogger(__name__)
console = Console(stderr=True)

# Checked first, in this order. Entertainment beats coding so that
# "Next.js drama - Twitter" isn't coding; documentation beats entertainment
# so that "Python tutorial - YouTube" counts as learning.
_PRIORITY = ("documentation", "entertainment", "coding")


def _keyword_pattern(keywords: list[str]) -> re.Pattern[str] | None:
    """One regex matching any keyword as a whole word.

    Guards are only added on alphanumeric ends, so ".py" still matches
    "main.py" while "zed" no longer matches "organized".
    """
    parts = [
        ("(?<![a-z0-9])" if k[0].isalnum() else "")
        + re.escape(k)
        + ("(?![a-z0-9])" if k[-1].isalnum() else "")
        for k in (kw.lower() for kw in keywords)
        if k
    ]
    return re.compile("|".join(parts)) if parts else None


class ActivityTracker:
    """Main activity tracking loop.

    Usage:
        tracker = ActivityTracker()
        tracker.start()  # Blocks until stop() is called
    """

    def __init__(self) -> None:
        self._config = load_config()
        self._stop_event = threading.Event()
        self._poll_interval = self._config.tracker.poll_interval
        self._last_hourly_snapshot = datetime.now()
        self._blocklist = self._config.security.blocklist
        self._idle_threshold = self._config.tracker.idle_threshold
        self._last_retention_day: date | None = None
        categories = self._config.tracker.app_categories
        order = [c for c in _PRIORITY if c in categories]
        order += [c for c in categories if c not in _PRIORITY]
        self._patterns = [
            (cat, pat) for cat in order if (pat := _keyword_pattern(categories[cat]))
        ]

    def start(self, daemon_mode: bool = False) -> None:
        """Start the tracking loop.

        Args:
            daemon_mode: If True, writes PID file and sets up signal handlers.
        """
        # Initialize the database
        init_db()

        if daemon_mode:
            self._write_pid_file()

        # Set up clean shutdown handlers
        signal.signal(signal.SIGTERM, self._handle_signal)
        signal.signal(signal.SIGINT, self._handle_signal)

        console.print("[green]✓[/green] FocusGuard tracker started")
        console.print(f"[dim]Polling every {self._poll_interval}s • Press Ctrl+C to stop[/dim]")

        try:
            self._run_loop()
        finally:
            if daemon_mode:
                self._remove_pid_file()
            console.print("\n[yellow]■[/yellow] FocusGuard tracker stopped")

    def stop(self) -> None:
        """Signal the tracker to stop gracefully."""
        self._stop_event.set()

    def _run_loop(self) -> None:
        """Main polling loop. Runs until stop_event is set."""
        while not self._stop_event.is_set():
            try:
                self._poll_tick()
            except Exception as e:
                # Never let the loop crash — log and continue
                logger.error(f"Error in poll tick: {e}", exc_info=True)

            # Wait for the next tick (or until stopped)
            self._stop_event.wait(timeout=self._poll_interval)

    def _poll_tick(self) -> None:
        """Execute a single poll tick: detect window → classify → log → score."""
        window = get_active_window()

        # Check if user is idle (no active window = likely locked screen)
        is_idle = window.is_unknown
        if not is_idle:
            is_idle = self._check_idle()

        # Sanitize the window title through the blocklist
        sanitized_title = sanitize_title(window.window_title, self._blocklist)

        # Classify the app into a category
        category = self._classify_app(window.app_name, sanitized_title)

        # Log to database
        log_activity(
            app_name=window.app_name,
            window_title=sanitized_title,
            category=category,
            duration_seconds=self._poll_interval,
            is_idle=is_idle,
        )

        # Snapshot session score on every tick
        snapshot_score("session")

        # Hourly snapshots
        now = datetime.now()
        if (now - self._last_hourly_snapshot) >= timedelta(hours=1):
            snapshot_score("hourly")
            self._last_hourly_snapshot = now

        # Once per calendar day (and on the first tick): retention + score pruning.
        # Marked before running so a failing policy is retried tomorrow, not every tick.
        if self._last_retention_day != now.date():
            self._last_retention_day = now.date()
            logger.info(f"Retention: {run_retention_policy()}")

        logger.debug(
            f"Tick: {window.app_name} [{category}]"
            f" {'(idle)' if is_idle else ''}"
        )

    def _classify_app(self, app_name: str, title: str | None) -> str:
        """Classify an application into a productivity category.

        The app name decides first ("Visual Studio Code" is coding whatever
        file is open). Browsers, and apps no keyword matches, are decided by
        the window title, so "YouTube" in Chrome is entertainment. Keywords
        match whole words only.
        """
        app_category = self._match(app_name)
        if app_category and app_category != "browser":
            return app_category
        return self._match(title) or app_category or "other"

    def _match(self, text: str | None) -> str | None:
        text = (text or "").lower()
        return next((cat for cat, pat in self._patterns if pat.search(text)), None)

    def _check_idle(self) -> bool:
        """True when there has been no keyboard/mouse input for idle_threshold seconds."""
        seconds = get_idle_seconds()
        return seconds is not None and seconds >= self._idle_threshold

    def _handle_signal(self, signum: int, frame: object) -> None:
        """Handle SIGTERM/SIGINT for graceful shutdown."""
        logger.info(f"Received signal {signum}, stopping...")
        self.stop()

    def _write_pid_file(self) -> None:
        """Write the current PID to the pid file."""
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        PID_FILE.write_text(str(os.getpid()))
        logger.info(f"PID file written: {PID_FILE}")

    def _remove_pid_file(self) -> None:
        """Remove the PID file on shutdown."""
        try:
            PID_FILE.unlink(missing_ok=True)
        except Exception:
            pass


def is_tracker_running() -> bool:
    """Check if a tracker instance is already running.

    Returns:
        True if the PID file exists and the process is alive.
    """
    if not PID_FILE.exists():
        return False

    try:
        pid = int(PID_FILE.read_text().strip())
        return psutil.pid_exists(pid)
    except (ValueError, OSError):
        # Stale or corrupt PID file — clean up
        PID_FILE.unlink(missing_ok=True)
        return False


def get_tracker_pid() -> int | None:
    """Get the PID of the running tracker, if any."""
    if not PID_FILE.exists():
        return None

    try:
        pid = int(PID_FILE.read_text().strip())
        if psutil.pid_exists(pid):
            return pid
    except (ValueError, OSError):
        pass

    return None
