# 06 — Roadmap

## v0.1.0: what exists

Poll loop, redaction, classification, scoring, dashboard, reports, goals, four personality modes,
Ollama/OpenAI coach, GitHub summary, local repo scan, three OS daemons, keyring-held secrets,
optional SQLCipher. 78 unit tests; CI is on the unmerged `fix/repository-review` branch. Known gaps: [05](05-known-issues.md).

## v0.2: make the numbers and the promises true

In order. Each item lists the issue it closes and the check that proves it.

| # | Change | Closes | Done when |
| --- | --- | --- | --- |
| 1 | Whole-word classification; sites before topics; app name before title | 05 #1 | The six titles in 05 #1 classify as entertainment, in a regression test |
| 2 | Real idle detection on macOS (`ioreg`), Windows (`GetLastInputInfo`), X11 (`xprintidle`) using `idle_threshold` | 05 #2 | Leaving the machine 10 min logs ≥ 9 idle minutes on macOS; other OSes [verify] |
| 3 | Run retention on date change; prune `session` scores | 05 #3 | Test: rows older than `retention_days` are summarised then gone |
| 4 | Persist `privacy blocklist add/remove` and `coach mode` | 05 #4, #9 | CLI tests with a temp HOME |
| 5 | Add `tomli-w`, delete the hand-written TOML writer | 05 #12 | Round-trip test with `\` and `"` in values |
| 6 | Sanitise `app_name` | 05 #6 | Test: blocklisted title on the fallback path stores no sensitive text |
| 7 | Rename the distribution before any PyPI publish | 05 #5 | `pip install <name>` installs this project |
| 8 | `ruff check --fix`, then the remaining ruff and mypy errors; CLI smoke tests | Code health | `ruff` and `mypy` clean in CI; coverage of `commands/` > 0 |

Items 1–3 change what the score means. Re-baseline any personal history after shipping them.

## v0.3: the features the README used to promise

| Change | Depends on | Done when |
| --- | --- | --- |
| Log commits from `[github] tracked_repos` hourly | v0.2 | Dashboard "Commits" and the week table show real per-day counts |
| Wire the procrastination engine into the tracker; show the verdict in `report`; optional nudge | idle detection, classification, git logging | Its verdict is shown with the signals that fired, and on 10 hand-labelled day-profiles it agrees with the labels in ≥ 8 |
| Re-weight signals so browser research with a goal isn't flagged | the labelled day-profiles above | The "reading docs" profile scores < 0.6 |
| Measure score validity | 2 weeks of v0.2 use | Rank correlation of daily score vs. 1–5 self-rating reported, against the plain productive-ratio baseline ([00](00-charter.md)) |

## Not planned

Cloud sync, team views, URL capture, app blocking. See the non-goals in [00](00-charter.md).
