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

`ActivityTracker._check_idle()` returns `False` unconditionally. The only idle signal is
"no window detected" (often a locked screen). `idle_threshold` in the config is read and ignored.
**Consequence:** walk away for an hour with your editor focused and FocusGuard logs an hour of
coding.

A real implementation needs seconds-since-last-input per OS, all reachable without new
dependencies:

| OS | Source |
| --- | --- |
| macOS | `ioreg -c IOHIDSystem` → `HIDIdleTime` (nanoseconds) |
| Windows | `ctypes.windll.user32.GetLastInputInfo` |
| Linux X11 | `xprintidle` if present, else treat as unknown |

## Classification (`ActivityTracker._classify_app`)

Search text is `f"{app_name} {title}".lower()`. Categories are checked in this order, and the first
category with **any keyword as a substring** wins:

1. `coding` → 2. `documentation` → 3. `entertainment` → 4. `browser`, `communication` (dict order) → `other`

Keyword lists are in `TrackerConfig.app_categories` (`config.py`) and replaceable from the config file.

**Why this misfires.** Short keywords match inside ordinary words, and coding is checked before
entertainment, so a coding keyword *anywhere* in a YouTube title wins:

| Title (in Chrome/Safari) | Matched keyword | Category |
| --- | --- | --- |
| How I Organized My Life - YouTube | `zed` in "organi**zed**" | coding |
| Anatomy of a scandal - Netflix | `atom` in "an**atom**y" | coding |
| Hyperpop mix - Spotify | `hyper` | coding |
| Next.js drama - Twitter | `.js` | coding |
| lofi beats to code to - YouTube | `code` | coding |
| Python memes - Reddit | `python` | documentation |

All six are reproducible with the snippet in [05](05-known-issues.md) #1. Fix direction:
whole-word matching (`re.search(rf"\b{re.escape(k)}\b", text)`), app-name rules before title
rules, and site names (YouTube, Netflix…) checked before topic words.

## Focus score (`core/scorer.py`)

For the window `[start, end]` (today by default), over non-idle rows:

```text
w(row)  = 2.0 if age ≤ 2h · 1.5 if ≤ 4h · 1.0 if ≤ 24h · 0.5 otherwise
P = Σ w·minutes over productive rows    productive  = coding, documentation, terminal
D = Σ w·minutes over distraction rows   distraction = entertainment
T = Σ w·minutes over all rows           neutral     = browser, communication, other (count in T only)

score = clamp( 100·P/T − 25·D/T , 0, 100 )
```

- Neutral time dilutes the score but isn't penalised. An hour in Slack drags the ratio down as
  much as an hour idle at the desk would, if idle were detected.
- `terminal` is listed as productive, but no keyword list produces it. Terminals are classified
  `coding` through their keywords.
- Week/month reports call the same function with `use_decay=False`, once per calendar day.

Labels: ≥90 Exceptional, ≥80 Focused, ≥65 Productive, ≥50 Average, ≥30 Distracted, else Off Track.

**Trend arrow:** the `hourly` snapshots from the last 8 hours, split in half. ↑ if the second half
averages more than 5 points higher, ↓ if more than 5 lower, else →.

**Snapshots:** every tick writes a `session` score row (today so far). Once an hour the tracker also
writes an `hourly` row (last 60 minutes). Each tick re-reads all of today's activity rows to compute
the score. That's cheap at 60 s polling, but it grows with the poll rate and the length of the day.

## Procrastination engine (`core/pattern_engine.py`), not wired in

Meant to flag compound patterns rather than "YouTube = bad". `detect_procrastination()` builds an
`ActivityContext` from the DB and sums the weights of the signals that fire. At ≥ 0.6 it counts as
procrastinating.

| Signal | Weight | Fires when |
| --- | --- | --- |
| `goal_set_no_progress` | 0.30 | active goal, 0 coding minutes in the last hour |
| `excessive_app_switching` | 0.20 | > 10 distinct apps in the last 30 min |
| `long_entertainment` | 0.40 | > 30 entertainment minutes in the last hour |
| `zero_git_activity` | 0.10 | no commits today, goal older than 2 h |
| `high_distraction_ratio` | 0.25 | distraction > coding and > 15 min in the last hour |
| `known_slump_hour` | 0.10 | this hour's 30-day average hourly score is > 10 below the mean |
| `long_idle_with_goal` | 0.35 | goal older than 1 h, < 5 coding and < 5 entertainment minutes in the last hour |

**Not called anywhere in the app**, only in `tests/test_pattern_engine.py`. No command shows its
result, and the tracker never triggers a nudge from it. Two things to settle before wiring it in:

- **It contradicts its own goal.** An hour reading docs in a browser with a goal set fires
  `goal_set_no_progress` (0.30) and `long_idle_with_goal` (0.35) = 0.65 → "procrastinating".
  That's exactly the false positive the module's docstring says it avoids. `coding_minutes_last_hour`
  only counts `coding` + `documentation` rows, so browser-category research reads as nothing.
- **`zero_git_activity` can never be false** while `git_activity` stays empty, so it adds 0.10 to
  every goal older than 2 hours.

Unit tests cover the arithmetic of each signal. None of them check that the weights give sensible
verdicts on realistic days. That needs a handful of labelled day-profiles (see [00](00-charter.md)).
