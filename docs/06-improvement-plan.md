# 06 — Improvement plan

Breaking changes are allowed: v0.1.0 has no published package and no users to migrate except the
author. Each phase lists what it fixes ([05](05-known-issues.md) numbers) and the check that
proves it's done. Work goes in order; a phase doesn't start until the one before has its checks.

## Phase 0 — done on `main` (unreleased)

| Change | Closes | Proven by |
| --- | --- | --- |
| Whole-word classifier, app name before title, no bare topic keywords | 05 #1 | `TestClassifierRegressions` |
| Idle detection from last-input time (macOS, Windows, X11) | 05 #2 | Unit test; one real macOS tick logged idle |
| Retention runs daily; `session` scores pruned; timestamp-format bug in retention | 05 #3 | `test_retention_summarises_and_prunes` |
| `privacy blocklist add/remove` and `coach mode` save the config | 05 #4, #9 | `tests/test_cli.py` |
| `tomli-w` replaces the hand-written TOML writer | 05 #12 | Round-trip test with `\` and `"` |
| App names go through the blocklist | 05 #6 | `test_blocklisted_app_name_is_redacted` |
| CI on Linux, macOS, Windows × Python 3.10, 3.12 | — | First green run after the next push |

## Phase 1 — every message tells the truth ✅

Small fixes where the CLI says something that isn't so. All done on `main`, each with a test except
the footer (checked in the regenerated `docs/images/report.svg`) and the warning (checked in a
terminal and through a pipe).

| Change | Closes | Done when |
| --- | --- | --- |
| `coach help` really falls back to the local summary when the LLM fails | 05 #13 | CLI test with a failing LLM prints the goal summary |
| `stats` "Since" shows the first activity today | 05 low | Test with activity starting 09:30 shows 9:30 AM |
| Unencrypted-DB warning once per process, never in the daemon log | 05 low | Two queries in one process print it once |
| `privacy show` stops claiming commit messages are tracked | 05 low | Text matches what is stored |
| `start -d` refuses when the OS daemon is installed (no restart loop) | 05 low | `start -d` with the plist present exits with a message |
| Dashboard footer sized to its content | 05 low | All 5 distractions visible at 38 lines |

## Phase 2 — code health

| Change | Done when |
| --- | --- |
| `ruff check --fix`, then the rest by hand | `ruff check src tests` clean, enforced in CI |
| Strict mypy errors fixed | `mypy src` clean, enforced in CI |
| A smoke test for every command (`--help` and one real run) | Coverage of `commands/` ≥ 80%, total ≥ 60% |

## Phase 3 — data safety (breaking)

| Change | Closes | Done when |
| --- | --- | --- |
| Schema migrations: numbered steps keyed off `schema_version` | — | A v1 database opens under v2 with data intact, in a test |
| Detect a plaintext DB when SQLCipher is present; `privacy encrypt` migrates it with `sqlcipher_export` | 05 #10 | Test: plain DB → encrypt → same rows readable |
| Decide: SQLCipher as a core dependency (encrypted by default) | 03 gap 1 | Decision recorded in [03](03-privacy-and-security.md) |
| Rename the distribution before any PyPI upload (e.g. `focusguard-cli`; the CLI command can stay `focusguard`) | 05 #5 | `pip install <name>` from TestPyPI installs this project |

## Phase 4 — measure before adding features

The score is a claim until these exist. This is the part of the project that makes it more than a
tracker, and the evidence a report or viva will ask for ([00](00-charter.md)).

| Change | Done when |
| --- | --- |
| `focusguard rate 1-5`: store a daily self-rating (new table, via a Phase 3 migration) | Rating saved and shown in `report -p week` |
| `scripts/export_titles.py`: distinct (app, title) pairs from your own DB to CSV for hand-labelling, titles already redacted | CSV of ≥ 200 rows labelled by hand |
| `scripts/eval_classifier.py`: per-category precision/recall against that CSV | Numbers in [02](02-tracking-and-scoring.md) |
| 15-minute walk-away test for idle detection | Minutes logged as active ≤ `idle_threshold` |
| `scripts/score_validity.py`: Spearman correlation of daily score vs rating, next to the plain productive-ratio baseline | Two weeks of data; both numbers reported, whichever wins |

## Phase 5 — classification v2 (only if Phase 4 shows it's needed)

| Change | Done when |
| --- | --- |
| `focusguard label <pattern> <category>`: user overrides, checked before defaults | Corrected titles reclassify; CLI test |
| Site rules from the browser title suffix (`… - YouTube`, `… - GitHub`) before keywords | Precision on the labelled set improves over Phase 4's numbers |

## Phase 6 — features the README used to promise

| Change | Depends on | Done when |
| --- | --- | --- |
| Log commits from `[github] tracked_repos` hourly | — | Dashboard "Commits" and the week table show real per-day counts |
| Wire the procrastination engine into `report`, with the signals that fired | Phases 4–5 | On 10 hand-labelled day-profiles it agrees with the labels in ≥ 8 |
| Re-weight so browser research with a goal isn't flagged | the day-profiles | The "reading docs" profile scores < 0.6 |

## Not planned

Cloud sync, team views, URL capture, app blocking. See the non-goals in [00](00-charter.md).
