# 02 — Tracking and scoring

## Window detection (`platform/window.py`)

1. **PyWinCtl** `getActiveWindow()`. App name from `getAppName()`, title from the window.
2. If that raises, a per-OS fallback:
   - macOS: AppKit `frontmostApplication()`. App name only, no title (pyobjc comes in with pywinctl).
   - Windows: `win32gui` (pywin32 comes in with pywinctl). App name is *guessed from the title*.
   - Linux: `xdotool getactivewindow getwindowname`. Same title-derived app name.
3. If everything fails, `app_name = "Unknown"`, and the tick is logged as idle.

`_extract_app_name` takes the text after the last ` — `, ` - `, ` – ` or ` | `. For
`"main.py — Visual Studio Code"` that's right. For a browser tab, `"Inbox (3) - Gmail - Google Chrome"`
gives `"Google Chrome"`. For a title with no separator, the whole title becomes the app name.

## Idle detection

A tick is idle when no window is detected (often a locked screen) or when there has been no
keyboard or mouse input for `idle_threshold` seconds (default 300). Idle ticks are logged but
left out of every score. `platform/idle.py` reads seconds-since-last-input with no new
dependencies:

| OS | Source | Checked |
| --- | --- | --- |
| macOS | `ioreg -c IOHIDSystem` → `HIDIdleTime` (nanoseconds) | Yes |
| Windows | `ctypes.windll.user32.GetLastInputInfo` vs `GetTickCount` | The call returns a reading on the Windows CI runners (CI run 46142584338); not yet tried on a desktop |
| Linux X11 | `xprintidle` if installed | The call returns a reading under `xvfb` in CI (CI run 46142584338); not yet tried on a desktop |
| Wayland, or any failure | none: the tick counts as not idle | — |

v0.1.0 had a stub here that always said "not idle", so an hour away from a focused editor logged an
hour of coding.

## Classification (`ActivityTracker._classify_app`)

Keywords match **whole words**, case-insensitively: `zed` matches "Zed" but not "organized".
A keyword that starts or ends with punctuation (`.py`) is only guarded on its letter side, so
`.py` still matches `main.py`.

0. Your own rules from `focusguard label PATTERN CATEGORY` (`[tracker.labels]`), matched against
   app name and title, longest pattern first. They beat everything below.
1. Match the **app name**. If it lands in any category other than `browser`, that's the answer:
   "Visual Studio Code" is coding even with `docs/README.md` open.
2. Otherwise (a browser, or an app no keyword knows) look at the **site named in the title's
   suffix**: the title is split on ` - `, ` — `, ` | `, ` · `, a trailing browser name is skipped,
   and the last remaining segment after the first is matched. "How do I parse YouTube URLs? -
   Stack Overflow" is coding, not entertainment. One exception: if the site is entertainment but
   the whole title matches documentation, documentation wins ("Python tutorial - YouTube").
3. No site match: match the whole **title**, checking categories in the order `documentation` →
   `entertainment` → `coding` → the rest in dict order.
4. No title match: the app's own category (`browser`), else `other`.

Labels and site rules are Phase 5 of [06](06-improvement-plan.md). Whether site rules raise
precision is unmeasured until you run `eval classifier` on labelled titles.

Documentation goes before entertainment so "Python tutorial - YouTube" counts as learning.
Entertainment goes before coding so "Next.js drama - Twitter" doesn't. Keyword lists are in
`TrackerConfig.app_categories` (`config.py`) and replaceable from the config file. The default
documentation list no longer contains bare topics (`python`, `react`, `rust`…), which made any
title that mentioned a language count as study.

**What v0.1.0 got wrong.** It matched substrings of `app name + title` and checked coding first,
so a coding keyword *anywhere* in a YouTube title won. All six now classify as entertainment
(`tests/test_tracker.py::TestClassifierRegressions`):

| Title (in Chrome/Safari) | v0.1.0 match | v0.1.0 category |
| --- | --- | --- |
| How I Organized My Life - YouTube | `zed` in "organi**zed**" | coding |
| Anatomy of a scandal - Netflix | `atom` in "an**atom**y" | coding |
| Hyperpop mix - Spotify | `hyper` | coding |
| Next.js drama - Twitter | `.js` | coding |
| lofi beats to code to - YouTube | `code` | coding |
| Python memes - Reddit | `python` | documentation |

Known remaining misfire: `course` makes "Of course I quit - YouTube" documentation. Title
keywords can't separate a lecture from a vlog reliably; measuring that is in [00](00-charter.md).

## Focus score (`core/scorer.py`)

For the window `[start, end]` (today by default), over non-idle rows:

```text
w(row)  = 2.0 if age ≤ 2h · 1.5 if ≤ 4h · 1.0 if ≤ 24h · 0.5 otherwise
P = Σ w·minutes over productive rows    productive  = coding, documentation, terminal
D = Σ w·minutes over distraction rows   distraction = entertainment
T = Σ w·minutes over all rows           neutral     = browser, communication, other (count in T only)

score = clamp( 100·P/T − 25·D/T , 0, 100 )
```

- Neutral time dilutes the score but isn't penalised. An hour in Slack drags the ratio down;
  an hour idle doesn't, because idle rows are excluded.
- `terminal` is listed as productive, but no keyword list produces it. Terminals are classified
  `coding` through their keywords.
- Week/month reports call the same function with `use_decay=False`, once per calendar day.

Labels: ≥90 Exceptional, ≥80 Focused, ≥65 Productive, ≥50 Average, ≥30 Distracted, else Off Track.

**Trend arrow:** the `hourly` snapshots from the last 8 hours, split in half. ↑ if the second half
averages more than 5 points higher, ↓ if more than 5 lower, else →.

**Snapshots:** every tick writes a `session` score row (today so far). Once an hour the tracker also
writes an `hourly` row (last 60 minutes). Each tick re-reads all of today's activity rows to compute
the score. That's cheap at 60 s polling, but it grows with the poll rate and the length of the day.

## Procrastination engine (`core/pattern_engine.py`)

Meant to flag compound patterns rather than "YouTube = bad". `detect_procrastination()` builds an
`ActivityContext` from the DB and sums the weights of the signals that fire. At ≥ 0.6 it counts as
procrastinating.

| Signal | Weight | Fires when |
| --- | --- | --- |
| `goal_set_no_progress` | 0.30 | active goal, 0 coding or documentation minutes in the last hour |
| `excessive_app_switching` | 0.20 | > 10 distinct apps in the last 30 min |
| `long_entertainment` | 0.40 | > 30 entertainment minutes in the last hour |
| `zero_git_activity` | 0.10 | no commits today, goal older than 2 h |
| `high_distraction_ratio` | 0.25 | distraction > coding and > 15 min in the last hour |
| `known_slump_hour` | 0.10 | this hour's 30-day average hourly score is > 10 below the mean |
| `long_idle_with_goal` | 0.35 | goal older than 1 h, < 5 non-idle minutes of any kind in the last hour |

**Shown on `focusguard report`** as a one-line "Procrastination check · last hour · unvalidated"
panel: the score, the 60% threshold, and the signals that fired. It doesn't trigger nudges.

- **Fixed: browser research with a goal.** v0.1.0's `long_idle_with_goal` counted only coding and
  entertainment minutes, so an hour of research in the `browser` category looked idle: 0.30 + 0.35
  = 0.65, flagged. It now counts every non-idle minute, and the same hour scores 0.40
  (`goal_set_no_progress` + `zero_git_activity`).
- **`zero_git_activity` always fires without `[github] tracked_repos`**, since there are no
  commits to see. It adds 0.10 to every goal older than 2 hours.
- **With no goal, entertainment alone flags.** `long_entertainment` + `high_distraction_ratio` =
  0.65. Whether an evening of YouTube with no goal should count is a judgment your labels should
  make.

`tests/test_pattern_engine.py::test_hour_profiles` pins the verdict on eight synthetic hours
(coding, browser research, docs, a YouTube binge, away from the desk, tab-hopping, entertainment
with no goal, a short break). Those are hours I wrote with the answer chosen in advance. They
check the rules do what they say, not that the rules are right. The real check is still Phase 6's:
your own labelled hours.
