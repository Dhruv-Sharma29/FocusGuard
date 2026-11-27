# Start here

From a fresh clone to a running tracker, then the optional pieces. Every command is listed in
[docs/04-cli-reference.md](docs/04-cli-reference.md).

## 1. Install

Python 3.10 or newer. FocusGuard is **not on PyPI**: `pip install focusguard` gets you an unrelated
package. Install from source.

```bash
git clone https://github.com/Dhruv-Sharma29/FocusGuard.git
cd FocusGuard
python3 -m venv .venv
source .venv/bin/activate            # Windows: .venv\Scripts\activate
pip install -e .                     # Linux x86_64: ".[encrypted]" for an encrypted database
focusguard --version                 # FocusGuard v0.1.0
```

Extras, combinable as `".[encrypted,ai,github]"`:

| Extra | Adds | Without it |
| --- | --- | --- |
| `encrypted` | SQLCipher (`sqlcipher3-binary`), so the database is encrypted with a key kept in the OS keyring. **Linux x86_64 only**: that package has no macOS or Windows wheels, so the extra fails to install there | Database is **plain SQLite**; commands that open it print a warning |
| `ai` | Ollama and OpenAI clients for `coach help` | Personality modes still work from local templates |
| `github` | GitPython and PyGithub for `github summary` / `github repos` | Those commands print an install hint |
| `dev` | pytest, ruff, mypy, types-psutil | — |

Want `focusguard` on your PATH outside the venv? `pipx install .` from the repo root.

**Encryption on macOS or Windows** [verify]: install the SQLCipher library (macOS:
`brew install sqlcipher`), then `pip install sqlcipher3`, which builds against it. FocusGuard uses
whichever `sqlcipher3` module is importable.

**Adding encryption later** is supported. An existing plain database keeps opening (with a
warning) until you run `focusguard stop` and then `focusguard privacy encrypt`, which copies it
into an encrypted file, checks every table's row count, and only then replaces the original. Back
up the key afterwards with `focusguard privacy export-key`.

## 2. Platform permissions

| OS | What to do |
| --- | --- |
| macOS | System Settings → Privacy & Security → **Accessibility** → add your terminal (Terminal, iTerm, Warp…). Without it you get app names but no window titles. `focusguard start` warns when the permission is missing. |
| Linux | Works on X11. On Wayland, window titles are mostly unavailable; the fallback uses `xdotool`, so install it. Install `xprintidle` too, or idle time isn't detected. |
| Windows | Works out of the box. Some antivirus tools flag any process that reads window titles. FocusGuard only reads the foreground window name; it doesn't inject into processes or read input. |

## 3. Track

```bash
focusguard start            # foreground, Ctrl+C to stop
focusguard start -d         # detached background process (stops on logout/reboot)
focusguard stop
```

Leave it running for a while, then:

```bash
focusguard stats            # one line
focusguard report           # full dashboard
focusguard report -p week   # 7-day table (also: month)
```

## 4. Survive reboots (daemon)

`start -d` stops at logout. To start automatically at login, install the OS service:

```bash
focusguard daemon install
focusguard daemon status
focusguard daemon uninstall
```

| OS | What `install` creates |
| --- | --- |
| macOS | `~/Library/LaunchAgents/com.focusguard.tracker.plist` (launchd; logs in `~/Library/Logs/focusguard/`) |
| Linux | `~/.config/systemd/user/focusguard.service` (systemd user unit) |
| Windows | Task Scheduler task `FocusGuard`, runs at logon via `pythonw.exe` |

With the daemon installed, `start -d` refuses and points you at `focusguard daemon status`. If you
start a foreground tracker first, the daemon's copy exits cleanly instead of restarting every 10 s.

## 5. Goals

```bash
focusguard goal add "Fix the login bug"
focusguard goal list            # --all includes done and dropped
focusguard goal complete 1
focusguard goal drop 2
```

The newest active goal is what the coach and nudges talk about.

## 6. Personality and AI coach

Nudges work without AI, using local templates filled in from your stats:

```bash
focusguard coach nudge          # in your configured mode
focusguard roast                # always roast mode
```

To change the default mode, set `[personality] mode` in the config file (step 8).
`focusguard coach mode <name>` does the same from the command line.

### Ollama (local, nothing leaves the machine)

```bash
pip install -e ".[encrypted,ai]"
ollama serve                    # in another terminal
ollama pull llama3.2:3b         # ~2 GB; smaller models answer faster but worse
focusguard coach enable --provider ollama
focusguard coach help           # uses your newest active goal
focusguard coach help -b        # break the goal into subtasks
```

### OpenAI (sends a short prompt to OpenAI's API)

```bash
focusguard coach setup-openai   # key goes to the OS keyring, not a file
focusguard coach enable --provider openai
```

What the prompt contains: your goal text, how long the goal has been open, your focus score, and
up to five recent app names. No window titles. See
[docs/03-privacy-and-security.md](docs/03-privacy-and-security.md#what-reaches-an-llm).

## 7. GitHub (optional)

```bash
pip install -e ".[encrypted,github]"
focusguard github setup         # paste a PAT; stored in the OS keyring
focusguard github summary -d 7  # commits, PRs, issues across your repos
focusguard github repos ~/Code  # scan local repos (default path ~/Code)
```

The CLI suggests a classic token with the `repo` scope. A fine-grained, read-only token limited to
the repositories you want counted is narrower and should be enough [verify].

## 8. Configuration

The config file is optional; every key has a default. Its location comes from `platformdirs`:

| OS | Config file | Database |
| --- | --- | --- |
| macOS | `~/Library/Application Support/focusguard/config.toml` | same folder, `focus.db` |
| Linux | `~/.config/focusguard/config.toml` | `~/.local/share/focusguard/focus.db` |
| Windows | `%LOCALAPPDATA%\focusguard\focusguard\config.toml` [verify] | `%LOCALAPPDATA%\focusguard\focusguard\focus.db` [verify] |

`focusguard privacy show` prints the exact paths on your machine. On macOS it is **not**
`~/.config/focusguard`; a file there is ignored.

```toml
[tracker]
poll_interval = 60          # seconds between polls
idle_threshold = 300        # seconds without keyboard/mouse input before a minute counts as idle

[security]
retention_days = 90         # older raw rows are summarised per day, then deleted (checked daily)
blocklist = ["chase", "paypal", "mychart", "incognito", "1password", "mybank"]
# Setting blocklist REPLACES the built-in list. Copy the defaults from
# src/focusguard/config.py and append, or you lose the built-in patterns.

[personality]
mode = "coach"              # coach | strict | friend | roast

[ai]
enabled = false
provider = "ollama"         # ollama | openai
ollama_model = "llama3.2:3b"
openai_model = "gpt-4o-mini"

[tracker.app_categories]
# Setting this table REPLACES ALL default categories, not just the ones you list.
# Define every category you want (coding, documentation, entertainment, browser, communication).
# Keywords match whole words: the app name first, then the window title for browsers.
coding = ["code", "pycharm", "terminal", "iterm", "xcode", "cursor"]
```

`coach enable`, `coach disable`, `coach mode` and `privacy blocklist add/remove` rewrite the whole file with every current value filled in.

## 9. Uninstall

```bash
focusguard privacy uninstall          # asks first; --yes skips the prompt
pip uninstall focusguard
```

That command stops the tracker, removes the daemon, deletes the data, config and log folders, and
clears the three keyring entries (DB key, GitHub token, OpenAI key). It can't be undone. If you
want to keep your history, export the DB key first with `focusguard privacy export-key` and copy
`focus.db` somewhere safe.

To pause without losing data: `focusguard stop && focusguard daemon uninstall`.
