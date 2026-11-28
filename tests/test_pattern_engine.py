"""Tests for the smart procrastination detection engine."""

import pytest

from focusguard.core.pattern_engine import (
    PROCRASTINATION_THRESHOLD,
    ActivityContext,
    DetectionResult,
    detect_procrastination,
    get_detection_summary,
)


class TestDetectProcrastination:
    def _make_context(self, **overrides) -> ActivityContext:
        """Create an ActivityContext with sensible defaults and overrides."""
        defaults = dict(
            has_active_goal=False,
            goal_description="",
            hours_since_goal_set=0.0,
            coding_minutes_last_hour=30.0,
            coding_minutes_today=120.0,
            active_minutes_last_hour=40.0,
            distraction_minutes_last_hour=5.0,
            entertainment_minutes_last_hour=5.0,
            unique_apps_last_30min=3,
            git_commits_today=5,
            focus_score=75.0,
            current_hour=10,
            avg_productive_hours=[9, 10, 11],
            avg_slump_hours=[14, 15],
        )
        defaults.update(overrides)
        return ActivityContext(**defaults)

    def test_productive_session_not_flagged(self):
        """Active coding with no distractions should not trigger."""
        ctx = self._make_context(
            has_active_goal=True,
            coding_minutes_last_hour=45,
            entertainment_minutes_last_hour=0,
            git_commits_today=3,
        )
        result = detect_procrastination(ctx)
        assert not result.is_procrastinating
        assert result.score < PROCRASTINATION_THRESHOLD

    def test_obvious_procrastination_flagged(self):
        """Goal set + no coding + lots of entertainment + app switching."""
        ctx = self._make_context(
            has_active_goal=True,
            hours_since_goal_set=3.0,
            coding_minutes_last_hour=0,
            entertainment_minutes_last_hour=45,
            distraction_minutes_last_hour=45,
            unique_apps_last_30min=15,
            git_commits_today=0,
        )
        result = detect_procrastination(ctx)
        assert result.is_procrastinating
        assert result.score >= PROCRASTINATION_THRESHOLD
        assert len(result.triggered_signals) >= 3

    def test_reading_docs_not_flagged(self):
        """Reading docs in a browser with a goal set should NOT trigger.

        This is the key differentiator from naive trackers.
        Browser time with no entertainment and some coding = research.
        """
        ctx = self._make_context(
            has_active_goal=True,
            hours_since_goal_set=1.0,
            coding_minutes_last_hour=15,  # some coding
            entertainment_minutes_last_hour=0,  # no entertainment
            distraction_minutes_last_hour=0,
            unique_apps_last_30min=3,  # few apps
            git_commits_today=2,
        )
        result = detect_procrastination(ctx)
        assert not result.is_procrastinating

    def test_no_goal_reduces_signals(self):
        """Without an active goal, goal-related signals don't fire."""
        ctx = self._make_context(
            has_active_goal=False,
            coding_minutes_last_hour=0,
            entertainment_minutes_last_hour=40,
        )
        result = detect_procrastination(ctx)
        # Should trigger entertainment but not goal-related signals
        goal_signals = [s for s in result.triggered_signals
                       if "goal" in s.name]
        assert len(goal_signals) == 0

    def test_slump_hour_contributes_small_weight(self):
        """Being in a slump hour alone shouldn't trigger procrastination."""
        ctx = self._make_context(
            current_hour=14,
            avg_slump_hours=[14, 15],
            coding_minutes_last_hour=20,
            entertainment_minutes_last_hour=5,
        )
        result = detect_procrastination(ctx)
        assert not result.is_procrastinating
        # But the slump signal should still be in triggered list
        slump_signals = [s for s in result.triggered_signals
                        if "slump" in s.name]
        assert len(slump_signals) == 1

    def test_custom_threshold(self):
        """A lower threshold should catch more cases."""
        ctx = self._make_context(
            has_active_goal=True,
            coding_minutes_last_hour=0,
            entertainment_minutes_last_hour=10,
        )
        # With default threshold, might not trigger
        result_default = detect_procrastination(ctx, threshold=0.6)
        # With very low threshold, should trigger
        result_low = detect_procrastination(ctx, threshold=0.1)
        assert result_low.score >= result_default.score  # Same score
        # Low threshold is more sensitive
        if result_default.score >= 0.1:
            assert result_low.is_procrastinating


class TestDetectionSummary:
    def test_no_procrastination_message(self):
        result = DetectionResult(
            score=0.2,
            is_procrastinating=False,
            triggered_signals=[],
            context=ActivityContext(),
        )
        summary = get_detection_summary(result)
        assert "No procrastination" in summary

    def test_procrastination_message_includes_signals(self):
        from focusguard.core.pattern_engine import SIGNALS

        result = DetectionResult(
            score=0.7,
            is_procrastinating=True,
            triggered_signals=SIGNALS[:2],
            context=ActivityContext(),
        )
        summary = get_detection_summary(result)
        assert "70%" in summary
        assert "Signals:" in summary


# Synthetic hour profiles with the verdict each one should get. They pin the engine's
# behaviour; they are NOT the Phase 4 validation, which needs your own labelled days.
_GOAL = dict(has_active_goal=True, hours_since_goal_set=3.0, git_commits_today=0)
PROFILES = [
    ("coding with a goal", dict(_GOAL, coding_minutes_last_hour=50,
                                active_minutes_last_hour=55), False),
    ("browser research, no keyword matched", dict(_GOAL, coding_minutes_last_hour=0,
                                                  active_minutes_last_hour=50), False),
    ("reading docs", dict(_GOAL, coding_minutes_last_hour=45,
                          active_minutes_last_hour=50), False),
    ("YouTube binge with a goal", dict(_GOAL, coding_minutes_last_hour=0,
                                       entertainment_minutes_last_hour=45,
                                       distraction_minutes_last_hour=45,
                                       active_minutes_last_hour=50), True),
    ("away from the desk with a goal", dict(_GOAL, coding_minutes_last_hour=0,
                                            active_minutes_last_hour=0), True),
    ("tab-hopping, no work", dict(_GOAL, coding_minutes_last_hour=0, unique_apps_last_30min=14,
                                  distraction_minutes_last_hour=20,
                                  entertainment_minutes_last_hour=20,
                                  active_minutes_last_hour=50), True),
    # Debatable: entertainment signals alone (0.4 + 0.25) flag it even with no goal set.
    # Pinned as current behaviour; your own labelled days should decide it.
    ("entertainment, no goal", dict(entertainment_minutes_last_hour=50,
                                    distraction_minutes_last_hour=50,
                                    active_minutes_last_hour=50), True),
    ("short break while coding", dict(_GOAL, coding_minutes_last_hour=40,
                                      entertainment_minutes_last_hour=10,
                                      distraction_minutes_last_hour=10,
                                      active_minutes_last_hour=55), False),
]


@pytest.mark.parametrize(("name", "fields", "expected"), PROFILES, ids=[p[0] for p in PROFILES])
def test_hour_profiles(name, fields, expected):
    result = detect_procrastination(ActivityContext(**fields))
    assert result.is_procrastinating is expected, (name, result.score)


def test_browser_research_scores_below_threshold():
    """v0.1.0 scored this 0.65 (goal_set_no_progress + long_idle_with_goal) and flagged it."""
    ctx = ActivityContext(**PROFILES[1][1])
    assert detect_procrastination(ctx).score < PROCRASTINATION_THRESHOLD
