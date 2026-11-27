"""focusguard start — Launch the activity tracker."""

from __future__ import annotations

import sys
from typing import Annotated

import typer
from rich.console import Console

console = Console()


def start(
    daemon: Annotated[
        bool,
        typer.Option("--daemon", "-d", help="Run as a background daemon."),
    ] = False,
    daemon_mode: Annotated[
        bool,
        typer.Option("--daemon-mode", hidden=True,
                     help="Internal flag: indicates process was launched by the daemon manager."),
    ] = False,
    allow_plaintext: Annotated[
        bool,
        typer.Option("--allow-plaintext", help="Track even though the database isn't encrypted."),
    ] = False,
) -> None:
    """Start tracking your productivity.

    By default, runs in the foreground (Ctrl+C to stop).
    Use --daemon to detach and run in the background.
    """
    if not daemon_mode:
        console.print(r"""[cyan]
 ███████╗ ██████╗  ██████╗██╗   ██╗███████╗
 ██╔════╝██╔═══██╗██╔════╝██║   ██║██╔════╝
 █████╗  ██║   ██║██║     ██║   ██║███████╗
 ██╔══╝  ██║   ██║██║     ██║   ██║╚════██║
 ██║     ╚██████╔╝╚██████╗╚██████╔╝███████║
 ╚═╝      ╚═════╝  ╚═════╝ ╚═════╝ ╚══════╝[/cyan]
 [dim]Guarding your focus...[/dim]
""")

    from focusguard.core.tracker import ActivityTracker, is_tracker_running

    # Check if already running
    if is_tracker_running():
        if daemon_mode:
            # Launched by launchd/systemd while a manual tracker runs: exit 0 so the
            # service manager doesn't restart us every few seconds.
            raise typer.Exit(0)
        console.print("[yellow]⚠ FocusGuard is already running.[/yellow]")
        console.print(
            "[dim]Use 'focusguard stop' first, or 'focusguard stats' to see current data.[/dim]"
        )
        raise typer.Exit(1)

    # A service-launched tracker exits 0 so launchd/systemd don't restart it every 10 s.
    require_encryption(allow_plaintext, exit_code=0 if daemon_mode else 1)

    # Check macOS permissions
    if sys.platform == "darwin":
        from focusguard.platform.window import check_accessibility_permissions
        if not check_accessibility_permissions():
            console.print(
                "[yellow]⚠ Accessibility permissions may be required "
                "for full window tracking.[/yellow]"
            )
            console.print(
                "[dim]Go to: System Settings → Privacy & Security → Accessibility[/dim]"
            )
            console.print(
                "[dim]Add your terminal app (Terminal, iTerm, Warp, etc.)[/dim]"
            )
            console.print()

    if daemon and not daemon_mode:
        from focusguard.commands.daemon import _get_platform_handler

        if _get_platform_handler().is_installed():
            console.print("[yellow]⚠ The daemon is installed and runs the tracker.[/yellow]")
            console.print("[dim]Check it with 'focusguard daemon status'.[/dim]")
            raise typer.Exit(1)
        _launch_daemon(allow_plaintext)
    else:
        # Run in foreground (or as daemon-mode subprocess)
        tracker = ActivityTracker()
        tracker.start(daemon_mode=daemon_mode)


def require_encryption(allow_plaintext: bool, exit_code: int = 1) -> None:
    """Refuse to track into an unencrypted database unless the user opted in."""
    from focusguard.db.connection import HAS_SQLCIPHER, is_encrypted

    if allow_plaintext or is_encrypted():
        return
    reason = (
        "it was created without encryption; run 'focusguard privacy encrypt'"
        if HAS_SQLCIPHER
        else "sqlcipher3 isn't installed (see start.md § 1)"
    )
    console.print(f"[red]✗ Not tracking into an unencrypted database: {reason}.[/red]")
    console.print("[dim]To track without encryption anyway, add --allow-plaintext.[/dim]")
    raise typer.Exit(exit_code)


def _launch_daemon(allow_plaintext: bool = False) -> None:
    """Launch FocusGuard as a detached background process."""
    import subprocess

    python = sys.executable
    cmd = [python, "-m", "focusguard", "start", "--daemon-mode"]
    if allow_plaintext:
        cmd.append("--allow-plaintext")

    try:
        # Launch detached subprocess
        if sys.platform == "win32":
            # Windows: use CREATE_NEW_PROCESS_GROUP
            process = subprocess.Popen(
                cmd,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                creationflags=subprocess.CREATE_NEW_PROCESS_GROUP | subprocess.DETACHED_PROCESS,  # type: ignore[attr-defined]
            )
        else:
            # Unix: double-fork to fully detach
            process = subprocess.Popen(
                cmd,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                start_new_session=True,
            )

        console.print(f"[green]✓[/green] FocusGuard daemon started (PID: {process.pid})")
        console.print(
            "[dim]Use 'focusguard stop' to stop, 'focusguard stats' for quick status.[/dim]"
        )

    except Exception as e:
        console.print(f"[red]✗ Failed to start daemon: {e}[/red]")
        raise typer.Exit(1) from None
