# FocusGuard

A local-first command-line tracker for developers. It records which app is in focus once a minute,
turns that into a 0–100 focus score, and shows the result as a terminal dashboard, with goals,
personality-mode nudges and an optional AI coach (Ollama locally, or OpenAI).

> **Status:** alpha (v0.1.0). The tracker, dashboard, reports, goals, personality modes, AI coach,
> GitHub summary, per-OS daemons, idle detection, 90-day retention and commit counting work. The
> **procrastination engine is written and unit-tested but not yet called by the app**, and
> classification is keyword-based, so some titles will land in the wrong category. See
> [Known issues](docs/05-known-issues.md) before trusting a score.

![FocusGuard dashboard](docs/images/report.svg)

<sub>All screenshots use synthetic demo data. Regenerate them with `python scripts/screenshots.py`.</sub>

## Architecture

```mermaid
flowchart LR
    subgraph LOOP[Tracker loop, every poll_interval seconds]
        direction LR
        W[platform/window.py<br/>active app + title] --> B[security/blocklist.py<br/>redact sensitive titles]
        B --> C[core/tracker.py<br/>classify into category]
        C --> DB[(SQLite<br/>activity_log)]
        DB --> S[core/scorer.py<br/>focus score snapshot]
        S --> FS[(focus_scores)]
    end
    DB --> UI[ui/dashboard.py · ui/report_view.py<br/>report, stats]
    FS --> UI
    DB --> P[personality/<br/>template nudges]
    P --> CO[coach nudge / roast]
    G[goal add] --> GL[(goals)]
    GL --> UI
    GL --> LLM[integrations/llm.py<br/>goal + time + app names only]
    LLM --> CO
    KR[OS keyring<br/>DB key, tokens] -.-> DB
    KR -.-> LLM
    KR -.-> GH[integrations/github_api.py]
```

Module map, schema and design rules: [docs/01-architecture.md](docs/01-architecture.md).

## What it looks like

| Quick stats and weekly report | Goals and roast mode |
| --- | --- |
| ![stats](docs/images/stats.svg) ![week](docs/images/report-week.svg) | ![goals](docs/images/goals.svg) ![roast](docs/images/roast.svg) |

<details>
<summary><code>focusguard privacy show</code> and <code>focusguard --help</code></summary>

![privacy](docs/images/privacy.svg)
![help](docs/images/help.svg)

</details>

## What works and what doesn't

| Feature | State | Where |
| --- | --- | --- |
| Active-window polling (macOS, Windows, Linux X11) | Works. macOS needs Accessibility permission. | `platform/window.py` |
| Sensitive-title redaction | Works on window titles and app names. Substring match, so it over-redacts. | `security/blocklist.py` |
| App classification | Whole-word keywords; app name first, then title for browsers. Keyword-based, so not exact. | `core/tracker.py` |
| Focus score with time decay | Works. Only as good as the classifier feeding it. | `core/scorer.py` |
| Dashboard, `stats`, week/month report | Works. "Commits" counts your commits in `[github] tracked_repos`. | `ui/` |
| Goals | Works. | `commands/goal.py` |
| Daily rating and self-evaluation | `rate 1-5`, `eval titles/classifier/score/idle`. Tools only: no measurements yet. | `commands/evaluate.py` |
| Personality modes (template messages) | Works. | `personality/` |
| AI coach (Ollama / OpenAI) | Works when enabled. | `integrations/llm.py` |
| GitHub summary, local repo scan | Works (`.[github]` extra). | `integrations/` |
| Background daemon | launchd, systemd user unit and Task Scheduler. | `platform/daemon_*.py` |
| Encrypted database | Only with SQLCipher installed (the `.[encrypted]` extra is Linux-only). The default install is **plain SQLite**; `privacy encrypt` converts an existing one. | `db/connection.py` |
| Idle detection | Works on macOS (checked). Windows and X11 (`xprintidle`) written, not yet run; none on Wayland. | `platform/idle.py` |
| Procrastination engine | **Not wired in.** Unit-tested, never called. | `core/pattern_engine.py` |
| 90-day retention | Works while the tracker runs: checked once a day, old rows summarised then deleted. | `core/retention.py` |
| Git commit logging | Works: tracker reads `git log` hourly for `tracked_repos`; SHA and time only. | `core/tracker.py` |

The details, with reproductions, are in [docs/05-known-issues.md](docs/05-known-issues.md). The fix
order is in [docs/06-improvement-plan.md](docs/06-improvement-plan.md).

## Run it

FocusGuard is **not on PyPI yet**; when it is, the package will be `focusguard-cli`
(`pip install focusguard` installs an unrelated project). Install from source:

```bash
git clone https://github.com/Dhruv-Sharma29/FocusGuard.git && cd FocusGuard
python3 -m venv .venv && source .venv/bin/activate
pip install -e .                     # extras: ".[ai,github]"; encryption: see start.md § 1
focusguard start --allow-plaintext  # foreground; Ctrl+C to stop (flag: no SQLCipher, see below)
focusguard report                    # in another terminal
```

`start` and `daemon install` refuse to track into an unencrypted database unless you pass
`--allow-plaintext`. SQLCipher installs from a wheel only on Linux x86_64, so on macOS and Windows
you'll normally need the flag ([start.md § 1](start.md#1-install)).

Step-by-step setup (daemon, AI coach, GitHub, config, uninstall): [start.md](start.md).
Every command: [docs/04-cli-reference.md](docs/04-cli-reference.md).

## Privacy in one paragraph

Everything stays on your machine unless you turn on the AI coach with the OpenAI provider or run a
`github` command. Window titles that match the blocklist are stored as `[private]`, secrets (DB key,
GitHub token, OpenAI key) live in the OS keyring, and there is no telemetry. One of the
privacy screen's own claims needs a caveat: the database is unencrypted unless you install the
`encrypted` extra. Full
account: [docs/03-privacy-and-security.md](docs/03-privacy-and-security.md).

## Development

```bash
pip install -e ".[dev]"
pytest                    # 169 tests, ~75% line coverage; every command has a smoke test
ruff check src tests      # clean; enforced in CI
mypy src                  # strict, clean; enforced in CI
python scripts/screenshots.py   # regenerate docs/images/
```

## Docs

Start with [start.md](start.md) to run it. The design record is in [docs/](docs/README.md):

| # | Doc | What it settles |
| --- | --- | --- |
| 00 | [Charter](docs/00-charter.md) | Problem, who it's for, scope, how success should be measured |
| 01 | [Architecture](docs/01-architecture.md) | Poll loop, module map, schema, design rules |
| 02 | [Tracking and scoring](docs/02-tracking-and-scoring.md) | Classification, the score formula, the procrastination engine |
| 03 | [Privacy and security](docs/03-privacy-and-security.md) | What is stored, redaction, encryption, what reaches an LLM |
| 04 | [CLI reference](docs/04-cli-reference.md) | Every command and option, config file location and keys |
| 05 | [Known issues](docs/05-known-issues.md) | Verified bugs and gaps, each with a reproduction |
| 06 | [Improvement plan](docs/06-improvement-plan.md) | What's done, what's next, and the check for each |

## License

MIT. See [LICENSE](LICENSE).
