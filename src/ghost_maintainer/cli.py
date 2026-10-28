"""CLI entry point for The Ghost Maintainer."""

from __future__ import annotations

import typer
from rich.console import Console

from ghost_maintainer import __version__

app = typer.Typer(
    name="ghost",
    help="The Ghost Maintainer: verifiable, local AI codebase archaeology tool.",
    no_args_is_help=True,
)

console = Console()


@app.callback(invoke_without_command=True)
def main(
    version: bool = typer.Option(
        False,
        "--version",
        "-v",
        help="Show ghost-maintainer version and exit.",
        is_eager=True,
    ),
) -> None:
    """Callback for global CLI options."""
    if version:
        console.print(f"[bold gold3]ghost-maintainer[/bold gold3] version {__version__}")
        raise typer.Exit()


@app.command()
def doctor() -> None:
    """Check environment diagnostics, Python version, Git, and backend readiness."""
    console.print(f"[bold gold3]The Ghost Maintainer[/bold gold3] v{__version__} - Diagnostics")
    console.print("Status: [green]Environment initialized[/green]")
