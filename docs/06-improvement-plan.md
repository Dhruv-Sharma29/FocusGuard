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
| CI on Linux, macOS, Windows × Python 3.10, 3.12 | — | Green on the push of `f16e5cd` |

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

## Phase 2 — code health ✅

Done on `main`: ruff and mypy clean and enforced by a `lint` CI job; 145 tests; coverage 73%
total and 89% for `commands/`.

| Change | Done when |
| --- | --- |
| `ruff check --fix`, then the rest by hand | `ruff check src tests` clean, enforced in CI |
| Strict mypy errors fixed | `mypy src` clean, enforced in CI |
| A smoke test for every command (`--help` and one real run) | Coverage of `commands/` ≥ 80%, total ≥ 60% |

## Phase 3 — data safety (breaking)

| Change | Closes | Done when |
| --- | --- | --- |
| ✅ Schema migrations: numbered steps keyed off `schema_version` | — | A v1 database opens under v2 with data intact, in a test |
| ✅ Detect a plaintext DB when SQLCipher is present; `privacy encrypt` migrates it with `sqlcipher_export` | 05 #10 | Test: plain DB → encrypt → same rows readable (real SQLCipher, `encrypted` CI job) |
| ✅ Decided: `start` and `daemon install` refuse plaintext without `--allow-plaintext` (a core SQLCipher dependency is ruled out: Linux-only wheels) | 03 gap 1 | Recorded in [03](03-privacy-and-security.md); refusal, daemon pass-through and no-restart-loop tested |
| ✅ Distribution renamed to `focusguard-cli`; command and import stay `focusguard` | 05 #5 | Builds and installs as `focusguard-cli` locally. Publishing (TestPyPI, then PyPI) not done: that's a release step for you to ask for |

## Phase 4 — measure before adding features

The score is a claim until these exist. This is the part of the project that makes it more than a
tracker, and the evidence a report or viva will ask for ([00](00-charter.md)).

**The tools are built** (on `main`, tested). They became CLI commands rather than scripts, so they
read the same config and database as everything else. **The measurements themselves are not done**:
they need your own data, and nobody else can collect it.

| Tool (✅ built) | Measurement still to do | Done when |
| --- | --- | --- |
| `focusguard rate 1-5 [--date] [--note]`: daily self-rating (schema v2, `ratings` table); shown in `report -p week` | Rate every day | — |
| `focusguard eval titles FILE.csv`: distinct (app, title) pairs with minutes and the current prediction; never overwrites | Label ≥ 200 rows by hand | CSV labelled |
| `focusguard eval classifier FILE.csv`: per-category precision/recall, exact accuracy, and productive/distraction/neutral accuracy | Run it on the labelled CSV | Numbers in [02](02-tracking-and-scoring.md) |
| `focusguard eval idle -m 20`: what was logged in the last N minutes | Walk away for 15 min with an editor focused, then run it | Minutes logged as active ≤ `idle_threshold` |
| `focusguard eval score`: Spearman ρ of daily score vs rating, next to the plain productive-ratio baseline | Two weeks of daily ratings | Both ρ reported, whichever wins |

With 14 days, a Spearman ρ needs to be above roughly 0.54 to be distinguishable from chance at
the usual 5% level [verify against a critical-value table], so treat small differences between the
two ρ values as noise.

## Phase 5 — classification v2

Built ahead of Phase 4's numbers because you asked for it; the second row's check still needs them.

| Change | Done when |
| --- | --- |
| ✅ `focusguard label <pattern> <category>`: user overrides, checked before defaults | ✅ Corrected titles reclassify in the tracker and `eval`; CLI test. Past rows keep their category |
| ✅ Site rules from the browser title suffix (`… - Stack Overflow`, `… - Reddit`) before title keywords | **Not yet**: precision on your labelled set must beat the keyword-only numbers. To compare, run `eval classifier` on this commit and on `73a321d` |

## Phase 6 — features the README used to promise

| Change | Depends on | Done when |
| --- | --- | --- |
| ✅ Log commits from `[github] tracked_repos` hourly | — | Dashboard "Commits" and the week table show real per-day counts |
| ✅ Wire the procrastination engine into `report`, with the signals that fired | Phases 4–5 | **Wired in; check not done.** Agreement on 10 of *your* labelled hours (≥ 8) still to measure. The 8 synthetic hours in `test_hour_profiles` only pin behaviour |
| ✅ Re-weight so browser research with a goal isn't flagged | — | ✅ The browser-research profile scores 0.40 (was 0.65); `test_browser_research_scores_below_threshold` |

## Open [verify] items

| Claim | Check | State |
| --- | --- | --- |
| Windows idle (`GetLastInputInfo`) | `tests/test_platform.py`, Windows CI runners | ✅ Passed (CI run 46142584338). A walk-away test on a real Windows desktop is still worth doing |
| X11 idle (`xprintidle`) | Same file, `encrypted` job under `xvfb` | ✅ Passed (CI run 46142584338) |
| Windows config/data paths in start.md § 8 | Same file, compares with `platformdirs` | ✅ Passed (CI run 46142584338) |
| macOS SQLCipher via `brew` + `sqlcipher3` | `encrypted-macos` CI job, non-blocking | ✅ Passed, including the encrypt round trip (CI run 46142584338) |
| SQLCipher on Windows | Not tried | Open |
| Fine-grained GitHub token is enough | Needs a real token | Yours to try |

## Not planned

Cloud sync, team views, URL capture, app blocking. See the non-goals in [00](00-charter.md).
