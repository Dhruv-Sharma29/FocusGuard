# FocusGuard — Documentation

A local-first CLI that samples the focused window once a minute, classifies it, and turns the log
into a focus score, a dashboard and personality-mode nudges.

These docs are the design record. Read them in order the first time and use them as reference
afterwards. To install and run, start with [start.md](../start.md).

## Reading order

| # | Doc | What it settles |
| --- | --- | --- |
| 00 | [Charter](00-charter.md) | The problem, who it's for, scope and non-goals, how success should be measured |
| 01 | [Architecture](01-architecture.md) | The poll loop, module map, schema, the design rules and where the code breaks them |
| 02 | [Tracking and scoring](02-tracking-and-scoring.md) | Window detection, classification, the score formula, the procrastination engine |
| 03 | [Privacy and security](03-privacy-and-security.md) | What is stored, redaction, encryption, keyring, what reaches an LLM or GitHub |
| 04 | [CLI reference](04-cli-reference.md) | Every command and option, config keys |
| 05 | [Known issues](05-known-issues.md) | Verified bugs and gaps, each with a reproduction and the fix |
| 06 | [Roadmap](06-roadmap.md) | Fix order and a definition of done for v0.2 |

## The one-paragraph version

Most time trackers either log everything (keystrokes, URLs, screenshots) or nothing useful. FocusGuard
aims for the middle: one sample a minute of *which app and window title is in front*, titles
redacted against a blocklist before they touch disk, stored locally, scored locally. What makes it
more than a logger is the scoring layer: a decayed productive-time ratio, and a weighted-signal
procrastination engine meant to tell "reading docs in a browser" from "drifting". Logging,
scoring, the UI, idle detection and retention work. The engine isn't wired in yet
([05](05-known-issues.md)), and the classifier is still the weakest link: the score is only as
honest as the category each sample gets.

## Status

v0.1.0: an initial commit plus a licence (a CI workflow exists only on the `fix/repository-review`
branch). The `docs/readme-refresh` branch adds fixes for the classifier, idle detection and
retention (05 #1–3). 86 unit tests pass on Python 3.12. Line coverage
is about 29%, and none of the CLI commands, UI renderers, integrations or daemons are under test.
Findings in these docs come from reading the code and running it on macOS on 2026-11-26. Windows and
Linux paths were read, not run.

## Conventions

- **[verify]** marks a claim not confirmed by running it on the platform in question.
- "Not wired in" means the function exists and may be unit-tested, but nothing in the CLI or
  tracker calls it.
- File references are relative to `src/focusguard/` unless they start with a top-level folder.
- Screenshots in `docs/images/` are generated from synthetic data by `scripts/screenshots.py`.
  They show real CLI output, not real usage numbers.
