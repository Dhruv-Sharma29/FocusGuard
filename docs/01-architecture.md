# 01 — Architecture

## One poll tick

```text
 every poll_interval s (default 60)                     core/tracker.py  ActivityTracker._poll_tick
 ┌────────────────────────────────────────────────────────────────────────────────────────────┐
 │ platform/window.py ─► security/blocklist.py ─► _classify_app ─► queries.log_activity ─►     │
 │ app name + title       title → "[private]"      category         activity_log row          │
 │ (PyWinCtl, then        if any pattern is a      (substring        (duration = poll         │
 │  AppKit / win32gui /   substring of it          keywords)         interval, is_idle)       │
 │  xdotool fallback)                                                                         │
 │                                                     ─► scorer.snapshot_score("session")     │
 │                                                        (+ "hourly" once an hour)           │
 └────────────────────────────────────────────────────────────────────────────────────────────┘
        │ activity_log, focus_scores, goals                       │
        ▼                                                         ▼
 ui/dashboard.py, ui/report_view.py              commands/coach.py ─► personality/ (templates)
 (report, stats)                                                   └─► integrations/llm.py (opt-in)
```

Nothing in the loop touches the network. Ticks never crash the loop: exceptions are logged and the
next tick runs. SIGTERM/SIGINT set a `threading.Event`, so `stop` takes effect within one wait.

## Module map

```text
src/focusguard/
├── main.py            Typer app; registers command groups and the hidden `roast` / `help-me` aliases
├── config.py          Dataclass config, TOML load/save, platformdirs paths
├── commands/          One file per command group; argument parsing and output only
├── core/
│   ├── tracker.py         Poll loop, classification, PID file
│   ├── scorer.py          Focus score, decay, trend, snapshots
│   ├── pattern_engine.py  Weighted procrastination signals (not wired in)
│   └── retention.py       Aggregate-then-delete old rows (not wired in)
├── db/
│   ├── connection.py  Thread-local connection; SQLCipher if installed, else sqlite3
│   ├── models.py      Schema v1, created on every command (idempotent)
│   └── queries.py     All SQL lives here
├── integrations/      git_tracker.py (GitPython), github_api.py (PyGithub), llm.py (Ollama/OpenAI)
├── personality/       modes.py (4 tones + templates), prompts.py (LLM system prompts)
├── platform/          window.py, daemon_macos.py / daemon_linux.py / daemon_windows.py
├── security/          blocklist.py, crypto.py (DB key), keyring_store.py (only keyring caller)
└── ui/                dashboard.py, report_view.py, themes.py (per-mode colours)
```

## Schema (v1, `db/models.py`)

| Table | Written by | Read by | Notes |
| --- | --- | --- | --- |
| `activity_log` | tracker, every tick | scorer, UI, coach | One row per tick. `timestamp` is local time as `YYYY-MM-DD HH:MM:SS`; `queries._ts()` formats every bound parameter the same way so string comparison works. |
| `focus_scores` | tracker: `session` every tick, `hourly` every hour | trend arrow, slump-hour learning | `session` rows are never pruned: ~1,440/day while tracking. |
| `goals` | `goal` commands | dashboard, coach | Newest active goal is "the" goal. |
| `git_activity` | **nothing** | dashboard "Commits", pattern engine, retention | `log_git_event()` has no caller, so this table stays empty. |
| `daily_summaries` | `retention.py` (never runs) | nothing | |
| `schema_version` | `init_db` | nothing | Version 1; there is no migration path yet. |

## Design rules, and where the code keeps them

**Rule 1: redact before persist.** The blocklist runs on the title before `log_activity`, so a
matching title is never written, even encrypted. *Kept for titles.* The `app_name` column isn't
filtered, and on the Windows/Linux fallback paths the app name is *derived from the title*
(`_extract_app_name`), so a sensitive title can land in `app_name` unredacted ([05](05-known-issues.md) #6).

**Rule 2: only `integrations/llm.py` sends activity data off the machine, and only on an explicit
`coach` command.** *Kept.* The daemon never calls an LLM. The payload is built field by field in
`commands/coach.py` and `personality/prompts.py`, never by serialising a row.

**Rule 3: only `security/keyring_store.py` talks to the keyring.** *Kept.* DB key, GitHub token
and OpenAI key all go through it.

**Rule 4: all SQL in `db/queries.py`.** *Mostly kept.* `core/retention.py` and
`core/pattern_engine.py` run their own `SELECT`s through `db.connection.query`. All of them are
parameterised. The one interpolated statement is `PRAGMA key`, built from a hex key the code
generates itself.

**Rule 5: commands are thin.** *Mostly kept.* `commands/coach.py` assembles score, goal and
recent-app context itself, so `nudge` and `help` duplicate gathering logic that belongs in `core/`.

## Process model

- `start` runs the tracker in the foreground.
- `start -d` re-launches `python -m focusguard start --daemon-mode` detached
  (`start_new_session=True` on Unix, `DETACHED_PROCESS` on Windows). The child writes
  `focusguard.pid` in the data dir.
- `daemon install` registers the same `--daemon-mode` command with launchd/systemd/Task Scheduler.
- `stop` reads the PID file and sends SIGTERM (Unix) or `terminate()` (Windows), then waits 5 s.
- One SQLite connection per thread, WAL mode, so `report` can read while the tracker writes.

## Where new code should go

| Adding | Put it in |
| --- | --- |
| A command | `commands/<group>.py`, registered in `main.py`; logic in `core/` |
| A procrastination signal | `SIGNALS` in `core/pattern_engine.py`, with a test in `tests/test_pattern_engine.py` |
| An LLM provider | a branch in `integrations/llm.py::chat` |
| A personality | `personality/modes.py` + `prompts.py` + `ui/themes.py` |
| Anything reading titles, secrets or the network | through `security/` or `integrations/llm.py`, never a second path |
