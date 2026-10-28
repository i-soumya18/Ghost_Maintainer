"""Tests for minimal CLI stub commands (doctor and --version)."""

from __future__ import annotations

from typer.testing import CliRunner

from ghost_maintainer import __version__
from ghost_maintainer.cli import app

runner = CliRunner()


def test_cli_version() -> None:
    """CLI --version displays version string and exits cleanly."""
    result = runner.invoke(app, ["--version"])
    assert result.exit_code == 0
    assert __version__ in result.stdout


def test_cli_doctor() -> None:
    """CLI doctor command prints diagnostics header."""
    result = runner.invoke(app, ["doctor"])
    assert result.exit_code == 0
    assert "Diagnostics" in result.stdout
    assert "Environment initialized" in result.stdout
