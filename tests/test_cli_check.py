"""End-to-end tests for the wired-up `irminsul check` command."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from typer.testing import CliRunner

from irminsul.cli import app

runner = CliRunner()


def test_check_good_fixture_exits_zero(
    fixture_repo: Callable[[str], Path],
) -> None:
    repo = fixture_repo("good")
    result = runner.invoke(app, ["check", "--scope", "hard", "--path", str(repo)])
    assert result.exit_code == 0, result.stdout
    assert "0 errors" in result.stdout


def test_check_bad_frontmatter_exits_one_with_findings(
    fixture_repo: Callable[[str], Path],
) -> None:
    repo = fixture_repo("bad-frontmatter")
    result = runner.invoke(app, ["check", "--scope", "hard", "--path", str(repo)])
    assert result.exit_code == 1
    assert "[frontmatter]" in result.stdout
    assert "missing frontmatter" in result.stdout


def test_check_bad_globs_exits_one_and_names_pattern(
    fixture_repo: Callable[[str], Path],
) -> None:
    repo = fixture_repo("bad-globs")
    result = runner.invoke(app, ["check", "--scope", "hard", "--path", str(repo)])
    assert result.exit_code == 1
    assert "[globs]" in result.stdout
    assert "app/missing/*.py" in result.stdout


def test_check_llm_flag_runs_without_error(fixture_repo: Callable[[str], Path]) -> None:
    repo = fixture_repo("good")
    result = runner.invoke(app, ["check", "--scope", "hard", "--llm", "--path", str(repo)])
    # --llm is now real; with no soft_llm configured and no API key it emits skip-info
    # or nothing — either way exit code should be 0 (info findings never block)
    assert result.exit_code == 0
