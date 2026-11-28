"""Configuration loader for FocusGuard.

Loads settings from ~/.config/focusguard/config.toml with sensible defaults.
Config file is optional — all defaults are baked into code.
"""

from __future__ import annotations

import dataclasses
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import tomli_w
from platformdirs import user_config_dir, user_data_dir, user_log_dir

if sys.version_info >= (3, 11):
    import tomllib
else:
    import tomli as tomllib


# ── Paths ────────────────────────────────────────────────────────────────────

APP_NAME = "focusguard"

CONFIG_DIR = Path(user_config_dir(APP_NAME))
DATA_DIR = Path(user_data_dir(APP_NAME))
LOG_DIR = Path(user_log_dir(APP_NAME))

CONFIG_FILE = CONFIG_DIR / "config.toml"
DB_FILE = DATA_DIR / "focus.db"
PID_FILE = DATA_DIR / "focusguard.pid"


# ── Dataclasses ──────────────────────────────────────────────────────────────


@dataclass
class TrackerConfig:
    """Settings for the activity tracker polling loop."""

    poll_interval: int = 60  # seconds between polls
    idle_threshold: int = 300  # seconds of no input before marking idle
    app_categories: dict[str, list[str]] = field(default_factory=lambda: {
        "coding": [
            "code", "visual studio", "vscode", "pycharm", "intellij", "webstorm",
            "sublime", "atom", "neovim", "vim", "emacs", "terminal", "iterm",
            "warp", "alacritty", "kitty", "hyper", "xcode", "android studio",
            "cursor", "zed", "electron",
            ".py", ".md", ".json", ".js", ".ts", ".rs", ".go", ".html", ".css",
            "leetcode", "github", "stackoverflow", "stack overflow",
        ],
        "browser": [
            "chrome", "firefox", "safari", "brave", "edge", "arc", "opera", "vivaldi",
        ],
        "communication": [
            "slack", "discord", "teams", "zoom", "telegram", "messages", "mail",
            "outlook", "thunderbird", "whatsapp",
        ],
        "entertainment": [
            "youtube", "netflix", "spotify", "twitch", "reddit", "twitter",
            "instagram", "tiktok", "hulu", "disney",
        ],
        "documentation": [
            "notion", "obsidian", "confluence", "docs", "wiki", "readme",
            "markdown", "pdf", "preview", "tutorial", "course", "lecture",
            "documentation", "learn code",
            # No bare topics ("python", "react"): they made "Python memes - Reddit" documentation.
        ],
    })
    # `focusguard label`: pattern -> category, checked before everything else.
    labels: dict[str, str] = field(default_factory=dict)


@dataclass
class SecurityConfig:
    """Settings for privacy and security."""

    blocklist: list[str] = field(default_factory=lambda: [
        # Banking (domain + display name patterns)
        "chase", "bankofamerica", "bank of america", "wellsfargo",
        "wells fargo", "capitalone", "capital one",
        "paypal", "venmo", "zelle", "schwab", "fidelity",
        # Healthcare
        "mychart", "healthcare", "medical", "patient portal",
        "pharmacy", "prescription", "health.gov",
        # Private browsing
        "private", "incognito",
        # Authentication
        "password", "signin", "sign in", "2fa", "authenticator",
        "1password", "bitwarden", "lastpass", "dashlane",
    ])
    retention_days: int = 90  # auto-delete raw logs older than this


@dataclass
class PersonalityConfig:
    """Settings for the personality / coaching mode."""

    mode: str = "coach"  # coach, strict, friend, roast


@dataclass
class AIConfig:
    """Settings for the AI coach integration."""

    enabled: bool = False
    provider: str = "ollama"  # ollama or openai
    ollama_model: str = "llama3.2:3b"  # small enough to run on most hardware (6GB RAM)
    openai_model: str = "gpt-4o-mini"


@dataclass
class GitHubConfig:
    """Settings for GitHub integration."""

    enabled: bool = False
    tracked_repos: list[str] = field(default_factory=list)


@dataclass
class FocusGuardConfig:
    """Root configuration object for FocusGuard."""

    tracker: TrackerConfig = field(default_factory=TrackerConfig)
    security: SecurityConfig = field(default_factory=SecurityConfig)
    personality: PersonalityConfig = field(default_factory=PersonalityConfig)
    ai: AIConfig = field(default_factory=AIConfig)
    github: GitHubConfig = field(default_factory=GitHubConfig)


# ── Loader ───────────────────────────────────────────────────────────────────


def _apply_dict_to_dataclass(dc: Any, data: dict[str, Any]) -> None:
    """Apply a dict of overrides onto a dataclass instance in-place."""
    for key, value in data.items():
        if hasattr(dc, key):
            current = getattr(dc, key)
            # If the field is itself a dataclass with a dict override, recurse
            if hasattr(current, "__dataclass_fields__") and isinstance(value, dict):
                _apply_dict_to_dataclass(current, value)
            else:
                setattr(dc, key, value)


def load_config() -> FocusGuardConfig:
    """Load configuration from TOML file, falling back to defaults.

    Returns a fully populated FocusGuardConfig.
    Missing keys use defaults; unknown keys are silently ignored.
    """
    config = FocusGuardConfig()

    if CONFIG_FILE.exists():
        with open(CONFIG_FILE, "rb") as f:
            raw = tomllib.load(f)
        _apply_dict_to_dataclass(config, raw)

    return config


def ensure_dirs() -> None:
    """Create required directories if they don't exist."""
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    DATA_DIR.mkdir(parents=True, exist_ok=True)


def save_config(config: FocusGuardConfig) -> None:
    """Save the configuration object back to the TOML file."""
    ensure_dirs()
    with open(CONFIG_FILE, "wb") as f:
        tomli_w.dump(dataclasses.asdict(config), f)
    LOG_DIR.mkdir(parents=True, exist_ok=True)
