# 03 — Privacy and security

FocusGuard's pitch is privacy, so this doc holds the code to the claims that `focusguard privacy show`
prints. Each row says whether the claim is true in v0.1.0.

## What is stored

| Data | Where | Notes |
| --- | --- | --- |
| Foreground app name | `activity_log.app_name` | Replaced by `[private]` like titles (v0.1.0 stored it unredacted). |
| Window title | `activity_log.window_title` | Replaced by `[private]` if any blocklist pattern is a substring. |
| Category, duration, idle flag | `activity_log` | One row per tick. |
| Focus score snapshots | `focus_scores` | ~1,440 `session` rows a day while tracking, pruned after a day. |
| Goals | `goals` | Free text you typed. |
| Git commits | `git_activity` | Only for repos in `[github] tracked_repos`, only your own (by the repo's `user.email`): repo folder name, SHA, commit time. No messages, file names or diffs. `github repos` and `github summary` compute and print without storing. |

Never collected anywhere in the code: keystrokes, clipboard, screenshots, URLs (beyond what a
browser puts in its window title), file contents, network traffic.

## The privacy screen's claims, checked

| Claim (`privacy show`) | True? | Detail |
| --- | --- | --- |
| Window titles are sanitised | **Yes**, for titles | Runs before the insert. Over-redacts: `"private"` and `"medical"` match "Private methods in Python" or "Medical imaging CNN paper.pdf". |
| Banking/health URLs never tracked | **Partly** | Only if the title contains a pattern. `paypal` is on the list; a bank not on it isn't. |
| Encryption | **Only with `[encrypted]`** | The default install uses `sqlite3`. The screen says "NOT encrypted" honestly, but the README used to say "SQLCipher AES-256" without the caveat. |
| Secrets in OS keyring | **Yes** | `security/keyring_store.py` is the only caller. |
| Telemetry: none | **Yes** | No network code runs except `coach help`/`nudge` (when AI is on), `github summary`, and the Ollama client (localhost). |
| Auto-delete after 90 days | **Yes, since the fix** | The tracker runs `core/retention.py` on its first tick and then daily: raw rows older than `retention_days` are summarised per day, then deleted. Not enforced while the tracker isn't running. v0.1.0 never called it. |
| `privacy blocklist add <p>` | **Yes, since the fix** | Saves to `[security] blocklist`. A running tracker picks it up on restart. v0.1.0 saved nothing. |

## Encryption at rest

With the `encrypted` extra, `db/connection.py` opens the file with SQLCipher and runs
`PRAGMA key = '<64 hex chars>'`. The key is 32 random bytes from `secrets.token_hex`, created on
first use and stored in the keyring under service `focusguard`, name `db_encryption_key`.

- `privacy export-key` prints the key so you can back it up. If the keyring entry is lost, the
  database can't be decrypted.
- On headless Linux without a Secret Service, keyring calls fail and the tracker can't open the
  encrypted DB [verify].
- A plain database is detected by its `SQLite format 3` header and keeps opening unencrypted, with
  a warning, until `privacy encrypt` converts it (copy with `sqlcipher_export`, compare every
  table's row count, then replace). v0.1.0 keyed it anyway and every query failed
  ([05](05-known-issues.md) #10). The round trip is tested against real SQLCipher in the
  `encrypted` CI job.
- `sqlcipher3-binary` ships Linux x86_64 wheels only, so the `encrypted` extra can't install on
  macOS or Windows.

## What reaches an LLM

Only on an explicit `coach help`, `coach nudge`, `coach roast` or `roast` with `[ai] enabled = true`:

| Command | Sent |
| --- | --- |
| `coach help` | Goal text, time since the goal was created, focus score, up to 5 distinct app names from the last 30 min |
| `coach help -b` | Goal text, time since the goal was created |
| `nudge` / `roast` | Focus score, coding and distraction minutes, top distraction's app name, goal text |

Plus a fixed per-mode system prompt (`personality/prompts.py`). With Ollama this stays on
`localhost`. With OpenAI it goes to OpenAI's API under your key.

The module docstring in `integrations/llm.py` says "last 3 app names". The code sends up to 5.
App names can contain title text on Windows/Linux, so they go through the blocklist too.

## Gaps, ranked

1. **Unencrypted by default.** Making SQLCipher a core dependency would break installs on macOS
   and Windows (no wheels). The remaining option is to have `start` refuse to run unencrypted
   without an explicit `--allow-plaintext`. Not decided yet ([06](06-improvement-plan.md) Phase 3).
2. **Substring blocklist.** Over-redacts common words, and nothing redacts unlisted sensitive sites.
   Whole-word matching fixes the first. For the second, consider an allowlist mode for titles
   (store titles only for categorised coding/docs apps).

## Reporting a vulnerability

Open a GitHub issue without exploit details and ask for a private channel, or use GitHub's
private vulnerability reporting if it's enabled on the repository.
