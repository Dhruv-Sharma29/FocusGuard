"""Tests for the activity tracker classification logic."""

from unittest.mock import MagicMock, patch

from focusguard.core.tracker import ActivityTracker


class TestAppClassification:
    """Test the app → category classification logic."""

    def setup_method(self):
        with patch("focusguard.core.tracker.load_config") as mock_config:
            config = MagicMock()
            config.tracker.poll_interval = 60
            config.tracker.idle_threshold = 300
            config.tracker.app_categories = {
                "coding": ["code", "vscode", "terminal", "iterm", "vim", "cursor", "zed"],
                "browser": ["chrome", "firefox", "safari", "arc"],
                "communication": ["slack", "discord", "zoom"],
                "entertainment": ["youtube", "netflix", "spotify", "reddit"],
                "documentation": ["notion", "obsidian", "docs"],
            }
            config.security.blocklist = []
            mock_config.return_value = config
            self.tracker = ActivityTracker()

    def test_classify_vscode(self):
        assert self.tracker._classify_app("Visual Studio Code", "main.py") == "coding"

    def test_classify_terminal(self):
        assert self.tracker._classify_app("Terminal", "zsh") == "coding"

    def test_classify_chrome(self):
        assert self.tracker._classify_app("Google Chrome", "Google Search") == "browser"

    def test_classify_youtube_in_browser(self):
        assert self.tracker._classify_app("Chrome", "YouTube - Video Title") == "entertainment"

    def test_classify_slack(self):
        assert self.tracker._classify_app("Slack", "#general") == "communication"

    def test_classify_notion(self):
        assert self.tracker._classify_app("Notion", "Project Wiki") == "documentation"

    def test_classify_unknown_app(self):
        assert self.tracker._classify_app("RandomApp", "Something") == "other"

    def test_classify_case_insensitive(self):
        """Classification should be case-insensitive."""
        assert self.tracker._classify_app("VISUAL STUDIO CODE", "FILE.PY") == "coding"

    def test_classify_cursor(self):
        assert self.tracker._classify_app("Cursor", "project") == "coding"

    def test_classify_spotify(self):
        assert self.tracker._classify_app("Spotify", "Playing music") == "entertainment"


def _tracker_with_defaults() -> ActivityTracker:
    """Tracker using the real default config, not a hand-written category dict."""
    from focusguard.config import FocusGuardConfig

    with patch("focusguard.core.tracker.load_config", return_value=FocusGuardConfig()):
        return ActivityTracker()


class TestClassifierRegressions:
    """Titles the v0.1.0 substring matcher got wrong (docs/05-known-issues.md #1)."""

    def setup_method(self):
        self.tracker = _tracker_with_defaults()

    def test_entertainment_titles_in_browser(self):
        for title in [
            "How I Organized My Life - YouTube",  # "zed" inside "organized"
            "Anatomy of a scandal - Netflix",     # "atom" inside "anatomy"
            "Hyperpop mix - Spotify",             # "hyper"
            "Next.js drama - Twitter",            # ".js"
            "lofi beats to code to - YouTube",    # "code"
            "Python memes - Reddit",              # "python" topic keyword
        ]:
            assert self.tracker._classify_app("Google Chrome", title) == "entertainment", title

    def test_learning_on_youtube_is_documentation(self):
        title = "Python tutorial - YouTube"
        assert self.tracker._classify_app("Google Chrome", title) == "documentation"

    def test_app_name_beats_title(self):
        title = "docs/README.md — FocusGuard"
        assert self.tracker._classify_app("Visual Studio Code", title) == "coding"

    def test_file_extensions_still_match(self):
        assert self.tracker._classify_app("RandomEditor", "main.py") == "coding"
        assert self.tracker._classify_app("Google Chrome", "paper.pdf") == "documentation"

    def test_plain_browsing_is_browser(self):
        assert self.tracker._classify_app("Google Chrome", "Weather forecast") == "browser"


class TestIdleAndRetention:
    def setup_method(self):
        self.tracker = _tracker_with_defaults()  # idle_threshold = 300

    def test_idle_uses_threshold(self):
        with patch("focusguard.core.tracker.get_idle_seconds", return_value=301):
            assert self.tracker._check_idle()
        with patch("focusguard.core.tracker.get_idle_seconds", return_value=10):
            assert not self.tracker._check_idle()
        with patch("focusguard.core.tracker.get_idle_seconds", return_value=None):
            assert not self.tracker._check_idle()

    def test_retention_runs_once_per_day(self):
        from focusguard.platform.window import WindowInfo

        window = WindowInfo("Code", "a.py")
        with (
            patch("focusguard.core.tracker.get_active_window", return_value=window),
            patch("focusguard.core.tracker.get_idle_seconds", return_value=0),
            patch("focusguard.core.tracker.run_retention_policy", return_value={}) as retention,
        ):
            self.tracker._poll_tick()
            self.tracker._poll_tick()
        assert retention.call_count == 1


def test_blocklisted_app_name_is_redacted():
    """On Windows/Linux the app name is cut from the title, so it must be redacted too."""
    from focusguard.config import FocusGuardConfig
    from focusguard.platform.window import WindowInfo

    config = FocusGuardConfig()
    with patch("focusguard.core.tracker.load_config", return_value=config):
        tracker = ActivityTracker()
    window = WindowInfo("Chase Online Banking", "Chase Online Banking")
    with (
        patch("focusguard.core.tracker.get_active_window", return_value=window),
        patch("focusguard.core.tracker.get_idle_seconds", return_value=0),
        patch("focusguard.core.tracker.run_retention_policy", return_value={}),
        patch("focusguard.core.tracker.log_activity") as log,
    ):
        tracker._poll_tick()
    assert log.call_args.kwargs["app_name"] == "[private]"
    assert log.call_args.kwargs["window_title"] == "[private]"


class TestSiteSuffixAndLabels:
    def setup_method(self):
        self.tracker = _tracker_with_defaults()

    def test_site_suffix_beats_title_keywords(self):
        title = "How do I parse YouTube URLs in Python? - Stack Overflow - Google Chrome"
        assert self.tracker._classify_app("Google Chrome", title) == "coding"

    def test_learning_on_entertainment_site_stays_documentation(self):
        title = "Rust tutorial - YouTube"
        assert self.tracker._classify_app("Google Chrome", title) == "documentation"

    def test_unknown_site_falls_back_to_keywords(self):
        title = "Notes on GitHub Actions caching - Some Blog"
        assert self.tracker._classify_app("Firefox", title) == "coding"

    def test_label_overrides_everything(self):
        from focusguard.config import FocusGuardConfig

        config = FocusGuardConfig()
        config.tracker.labels = {"figma": "coding", "rust book": "documentation"}
        with patch("focusguard.core.tracker.load_config", return_value=config):
            tracker = ActivityTracker()
        assert tracker._classify_app("Figma", "Landing page") == "coding"
        assert tracker._classify_app("Google Chrome", "The Rust Book - YouTube") == "documentation"
        assert tracker._classify_app("Google Chrome", "Cats - YouTube") == "entertainment"
