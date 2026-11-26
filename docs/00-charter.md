# 00 — Charter

## The problem

A developer finishes a day and can't say where the time went. Existing answers sit at two extremes:

- **Full trackers** (RescueTime-style tools, employer monitoring) log URLs, documents and sometimes
  screenshots, often to someone else's server. Accurate, but a privacy cost many people won't pay
  for self-insight.
- **Manual methods** (Pomodoro timers, time sheets) cost nothing in privacy but depend on the very
  discipline that's missing.

FocusGuard's bet: sampling **which app and window title is in front, once a minute**, redacting
sensitive titles, and keeping it all local gives enough signal for an honest daily picture, without
the surveillance.

## Who it's for

One developer, on their own machine, who wants feedback on their own habits. Not a team dashboard,
not employer monitoring. Nothing aggregates across users, and that's deliberate (see Non-goals).

## What it does

**Input:** the foreground window (app name + title) every `poll_interval` seconds, user-set goals,
optionally local git repos and the user's GitHub account.

**Output:**
1. A 0–100 focus score for today, with a trend arrow ([02](02-tracking-and-scoring.md)).
2. A dashboard: category breakdown, hourly timeline, top distractions, goals.
3. 7- and 30-day tables.
4. Nudges in one of four tones, from templates or from an LLM.

## Scope

### In
- macOS, Linux (X11) and Windows, through one cross-platform window API with per-OS fallbacks.
- Local SQLite storage, optionally SQLCipher-encrypted, key in the OS keyring.
- Opt-in AI coaching via a local model (Ollama) or OpenAI.
- Per-OS autostart (launchd, systemd user unit, Task Scheduler).

### Out (non-goals)
- Keystroke, clipboard, screen or URL capture.
- Any server, sync or multi-user feature.
- Blocking or killing apps. FocusGuard reports and nudges; it doesn't enforce.

## How success should be measured

None of these has been measured yet. They are the checks that would show whether the score means
anything; [06](06-roadmap.md) schedules them.

| Question | Measure | Why it matters |
| --- | --- | --- |
| Are samples labelled correctly? | Hand-label ~200 real window titles; report per-category precision/recall of `_classify_app` | Every number in the UI is downstream of this. All six entertainment titles tested in [05](05-known-issues.md) were labelled productive. |
| Is time away excluded? | Leave the machine for 15 min with an editor focused; count minutes logged as coding | Idle detection is a stub today, so this is currently 100% wrong |
| Does the score track how the user rated the day? | Daily 1–5 self-rating for two weeks vs. score; rank correlation | A score nobody agrees with gets ignored |
| Does the procrastination engine help? | Once wired in: share of alerts the user marks "fair" | Weighted rules are only useful if the weights are right |
| Overhead | CPU and memory of the daemon over a day; DB growth per day | It has to be forgettable to stay installed |

Baseline to beat: the plain productive-time ratio (coding + docs minutes / active minutes) with no
decay and no penalty. If the decayed, penalised score doesn't agree with self-ratings better than
that, the extra formula isn't earning its keep.
