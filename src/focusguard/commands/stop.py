"""focusguard stop — Stop the activity tracker."""

from __future__ import annotations

import psutil
import typer
from rich.console import Console

console = Console()


def stop() -> None:
    """Stop the FocusGuard tracker.

    Sends a graceful shutdown signal to the running tracker process.
    """
    from focusguard.config import PID_FILE
    from focusguard.core.tracker import get_tracker_pid

    pid = get_tracker_pid()

    if pid is None:
        console.print("[yellow]⚠ FocusGuard is not running.[/yellow]")
        raise typer.Exit(1)

    try:
        proc = psutil.Process(pid)
        proc.terminate()  # SIGTERM on Unix, TerminateProcess on Windows
        console.print(f"[green]✓[/green] Sent stop signal to FocusGuard (PID: {pid})")
        try:
            proc.wait(timeout=5)
            console.print("[green]✓[/green] FocusGuard stopped successfully")
        except psutil.TimeoutExpired:
            console.print("[yellow]⚠ Still running after 5 s.[/yellow]")

    except psutil.NoSuchProcess:
        # Process already dead, clean up PID file
        PID_FILE.unlink(missing_ok=True)
        console.print("[yellow]⚠ Process was already stopped. Cleaned up PID file.[/yellow]")

    except psutil.AccessDenied:
        console.print("[red]✗ Permission denied. Try running with elevated privileges.[/red]")
        raise typer.Exit(1) from None
