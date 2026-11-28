"""focusguard label — Correct the classifier with your own pattern -> category rules."""

from __future__ import annotations

from typing import Annotated

import typer
from rich.console import Console

from focusguard.config import load_config, save_config

console = Console()


def label(
    pattern: Annotated[
        str | None, typer.Argument(help="Whole word or phrase in the app name or window title.")
    ] = None,
    category: Annotated[
        str | None, typer.Argument(help="Category to give it, e.g. documentation.")
    ] = None,
    remove: Annotated[bool, typer.Option("--remove", "-r", help="Delete the rule.")] = False,
) -> None:
    """Classify everything matching PATTERN as CATEGORY, before the built-in rules.

    Examples: focusguard label "rust book" documentation · focusguard label figma coding ·
    focusguard label figma --remove · focusguard label (list rules).
    Applies to new activity once the tracker restarts, and to `eval titles` / `eval classifier`
    right away. Past rows keep their category.
    """
    config = load_config()
    labels = config.tracker.labels

    if pattern is None:
        if not labels:
            console.print("  No labels. Add one: focusguard label PATTERN CATEGORY")
        for p, c in sorted(labels.items()):
            console.print(f"  {p!r} → {c}")
        return

    pattern = pattern.strip().lower()
    if remove:
        if labels.pop(pattern, None) is None:
            console.print(f"[red]✗ No label for {pattern!r}.[/red]")
            raise typer.Exit(1)
        save_config(config)
        console.print(f"  [green]✓[/green] Removed {pattern!r}")
        return

    valid = sorted(set(config.tracker.app_categories) - {"browser"} | {"other"})
    if category not in valid:
        console.print(f"[red]✗ Category must be one of: {', '.join(valid)}.[/red]")
        raise typer.Exit(1)
    if not pattern:
        console.print("[red]✗ Pattern can't be empty.[/red]")
        raise typer.Exit(1)
    labels[pattern] = category
    save_config(config)
    console.print(f"  [green]✓[/green] {pattern!r} → {category}")
    console.print("  [dim]Restart the tracker (focusguard stop, then start) to apply it.[/dim]")
