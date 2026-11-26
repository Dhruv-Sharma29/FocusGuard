"""Tests for database operations."""

from datetime import datetime, timedelta

from focusguard.db import queries


class TestActivityLog:
    def test_log_activity(self, mock_db):
        row_id = queries.log_activity("VS Code", "main.py", "coding", 60, False)
        assert row_id > 0

    def test_get_today_activity(self, sample_activity):
        activity = queries.get_today_activity()
        assert len(activity) >= 9

    def test_get_coding_minutes(self, sample_activity):
        today = datetime.now().replace(hour=0, minute=0, second=0)
        minutes = queries.get_coding_minutes(today)
        # 4 coding entries × 60s = 240s = 4 minutes
        assert minutes >= 4.0

    def test_get_distraction_minutes(self, sample_activity):
        today = datetime.now().replace(hour=0, minute=0, second=0)
        minutes = queries.get_distraction_minutes(today)
        # 2 entertainment entries × 60s = 120s = 2 minutes
        assert minutes >= 2.0

    def test_get_top_distractions(self, sample_activity):
        distractions = queries.get_top_distractions(5)
        assert len(distractions) > 0
        assert all("app_name" in d for d in distractions)
        assert all("total_minutes" in d for d in distractions)

    def test_get_app_breakdown(self, sample_activity):
        breakdown = queries.get_app_breakdown()
        assert len(breakdown) > 0
        categories = [b["category"] for b in breakdown]
        assert "coding" in categories

    def test_idle_excluded_from_active_minutes(self, sample_activity):
        today = datetime.now().replace(hour=0, minute=0, second=0)
        total = queries.get_total_active_minutes(today)
        # 8 non-idle entries × 60s = 480s = 8 minutes
        assert total >= 8.0


class TestGoals:
    def test_add_goal(self, mock_db):
        goal_id = queries.add_goal("Build auth system")
        assert goal_id > 0

    def test_get_active_goals(self, sample_goals):
        goals = queries.get_active_goals()
        assert len(goals) == 2
        descriptions = [g["description"] for g in goals]
        assert "Build authentication system" in descriptions

    def test_complete_goal(self, sample_goals):
        assert queries.complete_goal(sample_goals[0])
        goals = queries.get_active_goals()
        assert len(goals) == 1

    def test_complete_nonexistent_goal(self, mock_db):
        assert not queries.complete_goal(9999)

    def test_drop_goal(self, sample_goals):
        assert queries.drop_goal(sample_goals[1])
        goals = queries.get_active_goals()
        assert len(goals) == 1

    def test_get_all_goals_includes_inactive(self, sample_goals):
        queries.complete_goal(sample_goals[0])
        all_goals = queries.get_all_goals(include_inactive=True)
        assert len(all_goals) == 2
        active_only = queries.get_all_goals(include_inactive=False)
        assert len(active_only) == 1


class TestFocusScores:
    def test_save_and_get_score(self, mock_db):
        queries.save_focus_score(75.5, 120.0, 30.0, 180.0, "session")
        score = queries.get_latest_score("session")
        assert score is not None
        assert score["score"] == 75.5
        assert score["coding_minutes"] == 120.0

    def test_score_trend(self, mock_db):
        for i in range(5):
            queries.save_focus_score(50.0 + i * 10, 60.0, 10.0, 80.0, "hourly")
        trend = queries.get_score_trend(hours=24)
        assert len(trend) == 5


class TestGitActivity:
    def test_log_git_event(self, mock_db):
        row_id = queries.log_git_event(
            "commit",
            repo_name="focusguard",
            details={"message": "Initial commit"},
        )
        assert row_id > 0

    def test_get_git_commits_today(self, mock_db):
        queries.log_git_event("commit", "focusguard")
        queries.log_git_event("commit", "focusguard")
        queries.log_git_event("pr_open", "focusguard")  # not a commit
        assert queries.get_git_commits_today() == 2

    def test_get_recent_git_activity(self, mock_db):
        queries.log_git_event("commit", "repo1")
        queries.log_git_event("pr_merge", "repo2")
        recent = queries.get_recent_git_activity(10)
        assert len(recent) == 2


def test_retention_summarises_and_prunes(mock_db):
    """Rows past retention_days are summarised then deleted; session scores past a day go."""
    from unittest.mock import patch

    from focusguard.config import FocusGuardConfig
    from focusguard.core.retention import run_retention_policy
    from focusguard.db.connection import execute, query

    old_day = (datetime.now() - timedelta(days=100)).strftime("%Y-%m-%d")
    for _ in range(3):
        queries.log_activity("Code", "a.py", "coding", 60, False)
    queries.log_activity("Code", "new.py", "coding", 60, False)
    execute(f"UPDATE activity_log SET timestamp = '{old_day} 10:00:00' WHERE window_title = 'a.py'")
    queries.save_focus_score(80.0, 3, 0, 3, "hourly")
    execute(f"UPDATE focus_scores SET timestamp = '{old_day} 10:30:00'")
    queries.save_focus_score(70.0, 1, 0, 1, "session")
    execute(
        "UPDATE focus_scores SET timestamp = datetime('now', 'localtime', '-2 days')"
        " WHERE period = 'session'"
    )
    queries.save_focus_score(75.0, 1, 0, 1, "session")  # today's, kept

    with patch("focusguard.core.retention.load_config", return_value=FocusGuardConfig()):
        result = run_retention_policy()

    assert result == {"days_summarized": 1, "activity_rows_deleted": 3, "score_rows_deleted": 2}
    summary = query("SELECT * FROM daily_summaries WHERE date = ?", (old_day,))[0]
    assert summary["coding_minutes"] == 3
    assert summary["avg_focus_score"] == 80.0  # found only with the space-separated timestamp
    assert [r["window_title"] for r in query("SELECT window_title FROM activity_log")] == ["new.py"]
    assert [r["score"] for r in query("SELECT score FROM focus_scores")] == [75.0]


def test_first_activity_time(mock_db):
    from datetime import datetime

    from focusguard.db.connection import execute

    today = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
    assert queries.get_first_activity_time(today) is None
    queries.log_activity("Code", "a.py", "coding", 60, False)
    queries.log_activity("Code", "b.py", "coding", 60, False)
    execute(f"UPDATE activity_log SET timestamp = '{today:%Y-%m-%d} 09:30:00' WHERE id = 1")
    execute(f"UPDATE activity_log SET timestamp = '{today:%Y-%m-%d} 11:00:00' WHERE id = 2")
    assert queries.get_first_activity_time(today) == today.replace(hour=9, minute=30)
