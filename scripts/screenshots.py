"""Regenerate the terminal screenshots in docs/images/.

Seeds a throwaway database with a week of synthetic activity in a temp HOME
(your real FocusGuard data is never touched), runs the real CLI, and exports
each command's coloured output as SVG with Rich.

    python scripts/screenshots.py

Run it during the day: "today" panels only show activity since midnight.
"""

from __future__ import annotations

import os
import random
import subprocess
import sys
import tempfile
from datetime import datetime, timedelta
from pathlib import Path

from rich.console import Console
from rich.text import Text

OUT = Path(__file__).resolve().parent.parent / "docs" / "images"
HOME = tempfile.mkdtemp(prefix="home-", dir="/tmp" if os.name != "nt" else None)
CLI = str(Path(sys.executable).parent / "focusguard")  # the installed entry point
ENV = {**os.environ, "HOME": HOME, "FORCE_COLOR": "1", "COLUMNS": "100", "LINES": "38",
       "PYTHONIOENCODING": "utf-8"}
os.environ["HOME"] = HOME  # before importing focusguard: its data paths are resolved at import

SHOTS = {  # file name -> CLI args
    "help": ["--help"],
    "stats": ["stats"],
    "report": ["report"],
    "report-week": ["report", "--period", "week"],
    "goals": ["goal", "list", "--all"],
    "roast": ["coach", "roast"],
    "privacy": ["privacy", "show"],
}

# (app, title, category, minutes) blocks that make up a plausible work day
DAY = [
    ("Code", "tracker.py — focusguard", "coding", 50),
    ("Google Chrome", "sqlite3 — Python docs", "documentation", 15),
    ("Slack", "#team", "communication", 10),
    ("Code", "scorer.py — focusguard", "coding", 45),
    ("Google Chrome", "YouTube", "entertainment", 20),
    ("iTerm2", "pytest", "coding", 25),
    ("Google Chrome", "Reddit", "entertainment", 10),
    ("Code", "dashboard.py — focusguard", "coding", 40),
]


def seed() -> None:
    from focusguard.db import queries
    from focusguard.db.connection import execute
    from focusguard.db.models import init_db

    init_db()
    rng = random.Random(7)
    now = datetime.now().replace(second=0, microsecond=0)

    def log_day(start: datetime, end: datetime) -> None:
        t = start
        while t < end:
            for app, title, cat, mins in DAY:
                for _ in range(rng.randint(mins // 2, mins)):
                    if t >= end:
                        return
                    execute(
                        "INSERT INTO activity_log (timestamp, app_name, window_title, category,"
                        " duration_seconds, is_idle) VALUES (?, ?, ?, ?, 60, 0)",
                        (t.strftime("%Y-%m-%d %H:%M:%S"), app, title, cat),
                    )
                    t += timedelta(minutes=1)

    for days_ago in range(6, 0, -1):
        day = (now - timedelta(days=days_ago)).replace(hour=9, minute=0)
        log_day(day, day + timedelta(hours=rng.randint(5, 8)))
    log_day(max(now.replace(hour=0, minute=0), now - timedelta(hours=5)), now)

    for h in range(8, 0, -1):  # hourly scores feed the trend arrow
        execute(
            "INSERT INTO focus_scores (timestamp, score, period) VALUES (?, ?, 'hourly')",
            ((now - timedelta(hours=h)).strftime("%Y-%m-%d %H:%M:%S"), 55 + 3 * (8 - h)),
        )

    queries.add_goal("Ship the weekly report view")
    queries.complete_goal(queries.add_goal("Write tests for the scorer"))
    queries.add_goal("Add idle detection on macOS")
    execute("UPDATE goals SET created_at = datetime(created_at, '-' || (id * 95) || ' minutes')")


def shoot(name: str, args: list[str]) -> None:
    run = subprocess.run([CLI, *args], env=ENV,
                         capture_output=True, text=True, encoding="utf-8")
    rec = Console(record=True, width=100, file=open(os.devnull, "w"))  # noqa: SIM115
    rec.print(Text.from_ansi(run.stdout.rstrip()))
    rec.save_svg(str(OUT / f"{name}.svg"), title=f"focusguard {' '.join(args)}")
    print(f"docs/images/{name}.svg")


if __name__ == "__main__":
    OUT.mkdir(parents=True, exist_ok=True)
    seed()
    for name, args in SHOTS.items():
        shoot(name, args)
