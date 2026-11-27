"""focusguard rate / focusguard eval — measure whether the score means anything."""

from __future__ import annotations

import csv
from collections.abc import Callable
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Annotated

import typer
from rich.console import Console
from rich.table import Table

from focusguard.db import queries
from focusguard.db.models import init_db

console = Console()
eval_app = typer.Typer(no_args_is_help=True)

CSV_FIELDS = ["app_name", "window_title", "minutes", "predicted", "label"]


def rate(
    rating: Annotated[int, typer.Argument(min=1, max=5, help="How focused the day felt, 1-5.")],
    day: Annotated[
        str | None, typer.Option("--date", "-d", help="YYYY-MM-DD (default: today).")
    ] = None,
    note: Annotated[str | None, typer.Option("--note", "-n", help="Optional note.")] = None,
) -> None:
    """Rate how focused today felt (1-5). Used by `focusguard eval score`."""
    try:
        when = date.fromisoformat(day) if day else date.today()
    except ValueError:
        console.print(f"  [red]✗ Not a date: {day} (use YYYY-MM-DD)[/red]")
        raise typer.Exit(1) from None
    init_db()
    queries.save_rating(when, rating, note)
    console.print(f"  [green]✓[/green] Rated {when:%a %d %b}: {rating}/5")


def _classifier() -> Callable[[str, str | None], str]:
    from focusguard.core.tracker import ActivityTracker

    return ActivityTracker()._classify_app


@eval_app.command("titles")
def export_titles(
    out: Annotated[Path, typer.Argument(help="CSV file to write (must not exist).")],
) -> None:
    """Export your distinct (app, window title) pairs to CSV for hand-labelling.

    Titles are as stored, so blocklisted ones are already '[private]'. The file holds
    your own window titles: keep it out of git and don't share it.
    """
    if out.exists():
        console.print(f"  [red]✗ {out} exists; refusing to overwrite your labels.[/red]")
        raise typer.Exit(1)
    init_db()
    classify = _classifier()
    rows = queries.get_distinct_titles()
    with open(out, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=CSV_FIELDS)
        writer.writeheader()
        for r in rows:
            writer.writerow({
                "app_name": r["app_name"],
                "window_title": r["window_title"] or "",
                "minutes": round(r["minutes"], 1),
                "predicted": classify(r["app_name"], r["window_title"]),
                "label": "",
            })
    console.print(f"  [green]✓[/green] Wrote {len(rows)} rows to {out}")
    console.print("  [dim]Fill in 'label' with a category, then: focusguard eval classifier[/dim]")


@eval_app.command("classifier")
def eval_classifier(
    labels: Annotated[Path, typer.Argument(help="CSV from `eval titles` with 'label' filled in.")],
) -> None:
    """Precision and recall of the current classifier against your labels."""
    from focusguard.config import load_config
    from focusguard.core.evaluation import classifier_report

    valid = {*load_config().tracker.app_categories, "other"}
    labelled, unknown = [], set()
    with open(labels, newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            label = (row.get("label") or "").strip().lower()
            if not label:
                continue
            if label not in valid:
                unknown.add(label)
                continue
            labelled.append((row["app_name"], row["window_title"] or None, label))
    if unknown:
        console.print(f"  [yellow]⚠ Skipped unknown labels: {', '.join(sorted(unknown))}[/yellow]")
        console.print(f"  [dim]Valid: {', '.join(sorted(valid))}[/dim]")
    if not labelled:
        console.print("  [red]✗ No labelled rows.[/red]")
        raise typer.Exit(1)

    report = classifier_report(labelled, _classifier())
    table = Table(title=f"Classifier vs {report.n} labels")
    for col in ("Category", "Labelled", "Predicted", "Precision", "Recall"):
        table.add_column(col, justify="left" if col == "Category" else "right")

    def pct(x: float | None) -> str:
        return "—" if x is None else f"{x:.0%}"

    for cat, s in report.per_category.items():
        table.add_row(cat, str(s.support), str(s.predicted), pct(s.precision), pct(s.recall))
    console.print(table)
    console.print(f"  Exact category accuracy: {report.accuracy:.0%}")
    console.print(f"  Productive / distraction / neutral accuracy: {report.group_accuracy:.0%}")
    if report.n < 200:
        console.print(f"  [dim]{report.n} labels; the plan asks for at least 200.[/dim]")


@eval_app.command("score")
def eval_score(
    days: Annotated[int, typer.Option("--days", "-d", help="Look back this many days.")] = 60,
) -> None:
    """Does the score track your daily ratings better than the plain productive ratio?"""
    from focusguard.core.evaluation import score_validity

    init_db()
    v = score_validity(days)
    table = Table(title=f"{len(v.rows)} rated days with activity")
    for col in ("Date", "Rating", "Score", "Baseline"):
        table.add_column(col, justify="right")
    for r in v.rows:
        table.add_row(f"{r.day:%a %d %b}", str(r.rating), f"{r.score:.0f}", f"{r.baseline:.0f}")
    console.print(table)

    def fmt(rho: float | None) -> str:
        return "undefined (fewer than 3 days, or no variation)" if rho is None else f"{rho:+.2f}"

    console.print(f"  Spearman ρ, focus score vs rating:       {fmt(v.score_rho)}")
    console.print(f"  Spearman ρ, productive ratio vs rating:  {fmt(v.baseline_rho)}")
    if len(v.rows) < 14:
        console.print(
            f"  [yellow]Only {len(v.rows)} days. Rate every day for two weeks before reading "
            "anything into this.[/yellow]"
        )
    console.print(
        "  [dim]The score earns its complexity only if its ρ is clearly higher than the "
        "baseline's.[/dim]"
    )


@eval_app.command("idle")
def eval_idle(
    minutes: Annotated[int, typer.Option("--minutes", "-m", help="Look back this far.")] = 20,
) -> None:
    """Show what the tracker logged in the last N minutes (for the walk-away test)."""
    init_db()
    rows = queries.get_activity_range(datetime.now() - timedelta(minutes=minutes))
    idle = sum(r["duration_seconds"] for r in rows if r["is_idle"]) / 60
    active = sum(r["duration_seconds"] for r in rows if not r["is_idle"]) / 60
    console.print(f"  Last {minutes} min: {active:.0f} min active, {idle:.0f} min idle")
    for r in rows[-minutes:]:
        flag = "idle" if r["is_idle"] else r["category"]
        console.print(f"  [dim]{r['timestamp']}  {flag:<14} {r['app_name']}[/dim]")
