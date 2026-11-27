"""Phase 4: daily ratings, classifier evaluation, score validity."""

from __future__ import annotations

import csv
from datetime import date, timedelta

import pytest
from typer.testing import CliRunner

from focusguard.core import evaluation as ev
from focusguard.db import queries
from focusguard.db.connection import execute
from focusguard.main import app

runner = CliRunner()


def _log_day(day: date, minutes: dict[str, int], idle: int = 0) -> None:
    """Log one row per category (duration = minutes), then move the new rows to `day`."""
    ids = [queries.log_activity("App", c, c, m * 60, False) for c, m in minutes.items()]
    if idle:
        ids.append(queries.log_activity("App", "idle", "coding", idle * 60, True))
    for row_id in ids:
        execute("UPDATE activity_log SET timestamp = ? WHERE id = ?", (f"{day} 10:00:00", row_id))


# ── Spearman ─────────────────────────────────────────────────────────────────


def test_spearman():
    assert ev.spearman([1, 2, 3, 4], [10, 20, 30, 40]) == pytest.approx(1.0)
    assert ev.spearman([1, 2, 3, 4], [4, 3, 2, 1]) == pytest.approx(-1.0)
    # Ties take the average rank: x ranks are [1, 2.5, 2.5, 4]; ρ = 4.5 / sqrt(4.5 * 5)
    assert ev.spearman([1, 2, 2, 3], [1, 2, 3, 4]) == pytest.approx(0.9487, abs=1e-4)
    assert ev.spearman([1, 2], [1, 2]) is None          # too few
    assert ev.spearman([5, 5, 5], [1, 2, 3]) is None    # constant


# ── Score validity ───────────────────────────────────────────────────────────


def test_day_metrics_matches_hand_calculation():
    day = date.today() - timedelta(days=3)
    _log_day(day, {"coding": 30, "entertainment": 10, "browser": 20}, idle=15)
    score, baseline = ev.day_metrics(day)
    assert baseline == pytest.approx(50.0)                   # 30 productive / 60 active
    assert score == pytest.approx(50.0 - 25 * 10 / 60)       # 100·P/T − 25·D/T
    assert ev.day_metrics(day - timedelta(days=1)) is None   # nothing logged


def test_score_validity_correlates_ratings():
    today = date.today()
    for offset, coding, rating in [(4, 10, 1), (3, 20, 2), (2, 40, 4), (1, 50, 5)]:
        day = today - timedelta(days=offset)
        _log_day(day, {"coding": coding, "browser": 60 - coding})
        queries.save_rating(day, rating)
    queries.save_rating(today - timedelta(days=6), 3)  # rated but no activity: skipped
    v = ev.score_validity(days=30, today=today)
    assert [r.rating for r in v.rows] == [1, 2, 4, 5]
    assert v.score_rho == pytest.approx(1.0)
    assert v.baseline_rho == pytest.approx(1.0)


# ── Classifier report ───────────────────────────────────────────────────────


def test_classifier_report():
    labelled = [
        ("Code", "a.py", "coding"),
        ("Chrome", "YouTube", "entertainment"),
        ("Chrome", "Docs", "documentation"),   # predicted coding: wrong category, same group
        ("Chrome", "Reddit", "entertainment"),  # predicted browser: wrong group too
    ]
    predictions = {"a.py": "coding", "YouTube": "entertainment", "Docs": "coding",
                   "Reddit": "browser"}
    r = ev.classifier_report(labelled, lambda app, title: predictions[title])
    assert r.n == 4
    assert r.accuracy == 0.5
    assert r.group_accuracy == 0.75
    assert r.per_category["coding"].precision == 0.5      # 1 of 2 predicted coding
    assert r.per_category["coding"].recall == 1.0
    assert r.per_category["entertainment"].recall == 0.5
    assert r.per_category["documentation"].precision is None  # never predicted


# ── CLI ──────────────────────────────────────────────────────────────────────


def test_rate_and_week_report():
    assert runner.invoke(app, ["rate", "4", "--note", "good day"]).exit_code == 0
    assert runner.invoke(app, ["rate", "2"]).exit_code == 0  # replaces today's rating
    assert queries.get_ratings(date.today(), date.today()) == {date.today(): 2}
    assert runner.invoke(app, ["rate", "6"]).exit_code != 0
    assert runner.invoke(app, ["rate", "3", "--date", "yesterday"]).exit_code == 1
    result = runner.invoke(app, ["report", "-p", "week"])
    assert result.exit_code == 0
    assert "Rated" in result.output


def test_titles_export_and_classifier_eval(tmp_path):
    queries.log_activity("Google Chrome", "How I Organized My Life - YouTube", "coding", 60, False)
    queries.log_activity("Visual Studio Code", "main.py", "coding", 120, False)
    out = tmp_path / "labels.csv"
    assert runner.invoke(app, ["eval", "titles", str(out)]).exit_code == 0
    rows = list(csv.DictReader(out.open(encoding="utf-8")))
    assert {r["predicted"] for r in rows} == {"entertainment", "coding"}  # current classifier
    assert runner.invoke(app, ["eval", "titles", str(out)]).exit_code == 1  # no overwrite

    for r in rows:
        r["label"] = "entertainment" if "YouTube" in r["window_title"] else "coding"
    rows.append({**rows[0], "label": "nonsense"})
    with out.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    result = runner.invoke(app, ["eval", "classifier", str(out)])
    assert result.exit_code == 0, result.output
    assert "Exact category accuracy: 100%" in result.output
    assert "nonsense" in result.output  # reported as skipped


def test_eval_score_and_idle():
    result = runner.invoke(app, ["eval", "score"])
    assert result.exit_code == 0
    assert "undefined" in result.output
    queries.log_activity("Code", "a.py", "coding", 60, True)
    result = runner.invoke(app, ["eval", "idle", "-m", "5"])
    assert result.exit_code == 0
    assert "1 min idle" in result.output
