# 05 — Known issues

Verified on macOS with Python 3.12 on 2026-11-26 against commit `0176c5a`. Ordered by how much
each one misleads the user. Issues 1–6, 8, 9, 10, 12 and 13, and the first five low-severity items, are fixed on `main`
(not yet released); their entries say what changed. Severity: **high** = numbers or privacy promises are wrong;
**medium** = a feature silently does nothing; **low** = cosmetic or edge case.

## High

### 1. Classifier calls entertainment "coding" — **fixed**
In v0.1.0, `core/tracker.py::_classify_app` matched keywords as substrings and checked `coding`
before `entertainment`. Every title below was classified as productive.

```bash
python -c "
from focusguard.core.tracker import ActivityTracker
t = ActivityTracker()
for title in ['How I Organized My Life - YouTube', 'Anatomy of a scandal - Netflix',
              'Hyperpop mix - Spotify', 'Next.js drama - Twitter',
              'lofi beats to code to - YouTube', 'Python memes - Reddit']:
    print(title, '->', t._classify_app('Google Chrome', title))"
```

v0.1.0 output: 5 × `coding`, 1 × `documentation`. Now all six print `entertainment`. **Fixed by**
whole-word matching, checking the app name before the title (browsers excepted), title priority
documentation → entertainment → coding, and dropping bare topic words (`python`, `react`…) from the
default documentation list. Regression tests: `tests/test_tracker.py::TestClassifierRegressions`.
Still possible: `course` matches "Of course I quit - YouTube" (documentation).

### 2. Idle time counts as work — **fixed**
In v0.1.0 `_check_idle()` returned `False`, so an unattended editor logged coding time all night.
It now compares per-OS seconds-since-last-input (`platform/idle.py`) with `idle_threshold`. Checked
on macOS by running the real tracker; on Windows and X11 the OS call works in CI, and Wayland has no source yet
([02](02-tracking-and-scoring.md#idle-detection)).

### 3. Retention never runs; score rows grow forever — **fixed**
In v0.1.0 `run_retention_policy()` had no caller, and a `session` score row was written every tick
and never deleted (~525k rows/year). The tracker now runs retention on its first tick and then once
per calendar day; retention also deletes `session` rows older than a day. Wiring it in exposed a
second bug, also fixed: retention compared stored timestamps (`YYYY-MM-DD HH:MM:SS`) with
`isoformat()` strings (`T` separator), so daily summaries never found their scores or commits and a
partly-summarised cutoff day could later be overwritten. Test: `tests/test_db.py::test_retention_summarises_and_prunes`.

### 4. Blocklist changes from the CLI are discarded — **fixed**
In v0.1.0 `privacy blocklist add/remove` printed a ✓ and saved nothing. They now update
`[security] blocklist` and save the config; `remove` of an unknown pattern exits 1. Test:
`tests/test_cli.py`.

### 5. `pip install focusguard` installs someone else's package — **fixed**
PyPI's `focusguard` is an unrelated project (v5.1.0), and the old README told users to run exactly
that. The distribution is now `focusguard-cli` (free on PyPI when checked on 2026-11-27; not yet
published). The import name and the `focusguard` command are unchanged. Install hints in the code
say `focusguard-cli[…]`.

### 6. App names bypass redaction — **fixed**
In v0.1.0 only `window_title` went through `sanitize_title`; now `app_name` does too. On the Windows/Linux fallbacks,
`_extract_app_name` builds the app name from the title. A title with no separator, like
`Chase Online Banking`, is stored verbatim as the app name and can reach the LLM in `coach help`.
Test: `test_blocklisted_app_name_is_redacted`.

## Medium

### 7. Procrastination engine isn't connected — **fixed**
v0.1.0 never called `core/pattern_engine.py`, and it flagged an hour of browser research with a
goal set (0.30 + 0.35 ≥ 0.6). `report` now shows its verdict and the signals that fired, and the
idle signal counts every active minute, so that hour scores 0.40. The weights are still
unvalidated; see [02](02-tracking-and-scoring.md#procrastination-engine-corepattern_enginepy).

### 8. Git activity is never recorded — **fixed**
In v0.1.0 nothing wrote `git_activity`, so "Commits" was always 0, `zero_git_activity` always fired,
and the week report repeated today's count on every row. Now the tracker reads your commits from
`[github] tracked_repos` with `git log --all --author=<user.email>` (no extra package) on its first
tick and then hourly, logs each SHA once at its commit time, and the week report counts per day.
Only repo name, SHA and time are stored. Tests: `tests/test_git_commits.py` (a real temp repo).

### 9. `coach mode` doesn't persist — **fixed**
v0.1.0 printed "Switched to … mode" without saving. It now writes `[personality] mode`.

### 10. Adding SQLCipher later breaks the existing database — **fixed**
In v0.1.0 `_get_connection` keyed the database whenever `sqlcipher3` was importable, so a database
created without it failed every query with "file is not a database". Now a plain file (header
`SQLite format 3`) opens unencrypted with a warning, and `privacy encrypt` converts it in place
after verifying row counts. Tests: `tests/test_storage.py`; the real-SQLCipher round trip runs in
the `encrypted` CI job, because `sqlcipher3-binary` has Linux wheels only.

### 11. Docs pointed macOS users at the wrong config path
The config lives at `~/Library/Application Support/focusguard/config.toml` on macOS
(`platformdirs`). The old SETUP/README said `~/.config/focusguard/`, which is ignored there.
Fixed in these docs. `privacy show` prints the real path.

### 12. Saving the config corrupts it for some values — **fixed**
`tomli-w` is now a dependency and the hand-written writer is gone. In v0.1.0 `tomli_w` wasn't a
dependency, so `save_config` always used a hand-written TOML emitter that doesn't
escape strings. Reproduce: add a blocklist entry or tracked repo containing `\` (any Windows path),
run `coach enable`, then any command → `TOMLDecodeError`. Test: `test_config_round_trips_backslash_and_quote`.

### 13. `coach help` claims a fallback it doesn't do — **fixed**
v0.1.0 printed "Falling back to local mode." on an LLM error and showed nothing. It now prints the
local goal summary. Test: `test_coach_help_falls_back_when_llm_fails`.

## Low

- **Fixed:** `stats` printed "Since 12:00 AM" regardless of when tracking started; it now shows the
  first activity today.
- **Fixed:** the dashboard footer was fixed at 7 lines, cutting off "Top Distractions"; it is now
  sized to its rows.
- **Fixed:** `start -d` with the launchd daemon installed made launchd restart the daemon's tracker
  every 10 s. `start -d` now refuses, and a daemon-launched tracker exits 0 if one is running.
- **Fixed:** the unencrypted-DB warning printed once per thread, including into the daemon's log. It
  now prints once per process, and only to a terminal.
- **Fixed:** `privacy show` said git commit *messages* are tracked; nothing stores them.
- `terminal` is listed as a productive category, but no keyword list produces it.

## Code health

| Check | Result |
| --- | --- |
| `pytest` | 168 passed, 1 skipped without SQLCipher (78 in v0.1.0) |
| Line coverage | 75% (25% in v0.1.0). `commands/` 89%. Lowest: `platform/daemon_*` 0%, `llm.py` 21%, `github_api.py` 26%, `idle.py` 28%, `window.py` 32% (OS and network code, mocked at the command level) |
| `ruff check src tests` | Clean, enforced in CI (94 findings in v0.1.0). `RUF001`–`003` are ignored: the en dashes and × are deliberate |
| `mypy src` (strict, `platform = "linux"`) | Clean, enforced in CI (31 errors in v0.1.0) |

Every command has a `--help` test and at least one real run (`tests/test_commands_smoke.py`).
An autouse fixture in `tests/conftest.py` points every FocusGuard path at a temp folder and swaps the
OS keyring for a dict, so no test can touch real data, a running tracker or your keychain.
