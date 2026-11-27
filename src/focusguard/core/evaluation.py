"""Checks that say whether the score means anything (docs/00-charter.md).

- classifier_report: precision/recall of the classifier against hand labels.
- score_validity: does the daily score track the user's own 1-5 rating better than
  the plain productive-minutes ratio does?
"""

from __future__ import annotations

import statistics
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta

from focusguard.core.scorer import (
    DISTRACTION_CATEGORIES,
    PRODUCTIVE_CATEGORIES,
    calculate_focus_score,
)
from focusguard.db import queries


def _ranks(values: list[float]) -> list[float]:
    """1-based ranks; ties get the average of the ranks they span."""
    order = sorted(range(len(values)), key=values.__getitem__)
    ranks = [0.0] * len(values)
    i = 0
    while i < len(order):
        j = i
        while j + 1 < len(order) and values[order[j + 1]] == values[order[i]]:
            j += 1
        for k in range(i, j + 1):
            ranks[order[k]] = (i + j) / 2 + 1
        i = j + 1
    return ranks


def spearman(xs: list[float], ys: list[float]) -> float | None:
    """Spearman rank correlation, or None when undefined (n < 3 or a constant series)."""
    if len(xs) != len(ys) or len(xs) < 3:
        return None
    try:
        return statistics.correlation(_ranks(xs), _ranks(ys))
    except statistics.StatisticsError:
        return None


# ── Score validity ───────────────────────────────────────────────────────────


@dataclass
class DayRow:
    day: date
    rating: int
    score: float      # what `report -p week` shows for the day (no decay)
    baseline: float   # productive minutes / active minutes x 100


def day_metrics(day: date) -> tuple[float, float] | None:
    """(score, baseline) for a day, or None if nothing active was logged."""
    start = datetime.combine(day, time.min)
    end = datetime.combine(day, time.max)
    rows = [r for r in queries.get_activity_range(start, end) if not r["is_idle"]]
    total = sum(r["duration_seconds"] for r in rows)
    if total == 0:
        return None
    productive = sum(r["duration_seconds"] for r in rows if r["category"] in PRODUCTIVE_CATEGORIES)
    return calculate_focus_score(start, end, use_decay=False), 100 * productive / total


@dataclass
class Validity:
    rows: list[DayRow]
    score_rho: float | None
    baseline_rho: float | None


def score_validity(days: int = 60, today: date | None = None) -> Validity:
    """Rated days with activity in the last `days` days, and both correlations."""
    end = today or date.today()
    ratings = queries.get_ratings(end - timedelta(days=days - 1), end)
    rows = []
    for day, rating in ratings.items():
        metrics = day_metrics(day)
        if metrics:
            rows.append(DayRow(day, rating, *metrics))
    rated = [float(r.rating) for r in rows]
    return Validity(
        rows,
        spearman([r.score for r in rows], rated),
        spearman([r.baseline for r in rows], rated),
    )


# ── Classifier ───────────────────────────────────────────────────────────────


@dataclass
class CategoryStats:
    support: int     # labelled rows with this label
    predicted: int   # rows the classifier put here
    correct: int

    @property
    def precision(self) -> float | None:
        return self.correct / self.predicted if self.predicted else None

    @property
    def recall(self) -> float | None:
        return self.correct / self.support if self.support else None


def _group(category: str) -> str:
    if category in PRODUCTIVE_CATEGORIES:
        return "productive"
    if category in DISTRACTION_CATEGORIES:
        return "distraction"
    return "neutral"


@dataclass
class ClassifierReport:
    per_category: dict[str, CategoryStats]
    n: int
    accuracy: float
    group_accuracy: float  # productive / distraction / neutral: what the score actually uses


def classifier_report(
    labelled: Iterable[tuple[str, str | None, str]],
    classify: Callable[[str, str | None], str],
) -> ClassifierReport:
    """Compare classify(app, title) with hand labels."""
    stats: dict[str, CategoryStats] = {}
    n = correct = group_correct = 0
    for app, title, label in labelled:
        predicted = classify(app, title)
        n += 1
        for cat in (label, predicted):
            stats.setdefault(cat, CategoryStats(0, 0, 0))
        stats[label].support += 1
        stats[predicted].predicted += 1
        if predicted == label:
            stats[label].correct += 1
            correct += 1
        group_correct += _group(predicted) == _group(label)
    return ClassifierReport(
        dict(sorted(stats.items())),
        n,
        correct / n if n else 0.0,
        group_correct / n if n else 0.0,
    )
