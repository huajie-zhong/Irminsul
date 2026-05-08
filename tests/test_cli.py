"""Smoke tests for the CLI surface."""

from __future__ import annotations

from typer.testing import CliRunner

from irminsul import __version__
from irminsul.cli import app

runner = CliRunner()


def test_version_flag() -> None:
    result = runner.invoke(app, ["--version"])
    assert result.exit_code == 0
    assert __version__ in result.stdout


def test_help_lists_commands() -> None:
    result = runner.invoke(app, ["--help"])
    assert result.exit_code == 0
    for cmd in ("init", "check", "render"):
        assert cmd in result.stdout


def test_check_rejects_unknown_scope() -> None:
    result = runner.invoke(app, ["check", "--scope", "wat"])
    assert result.exit_code != 0
