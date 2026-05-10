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


def test_check_rejects_unknown_profile() -> None:
    result = runner.invoke(app, ["check", "--profile", "wat"])
    assert result.exit_code != 0


def test_check_rejects_removed_scope() -> None:
    result = runner.invoke(app, ["check", "--scope", "hard"])
    assert result.exit_code != 0


def test_check_rejects_removed_llm_flag() -> None:
    result = runner.invoke(app, ["check", "--llm"])
    assert result.exit_code != 0
