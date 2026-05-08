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


def test_check_format_json_produces_valid_json(
    fixture_repo: Callable[[str], Path],
) -> None:
    import json

    repo = fixture_repo("good")
    result = runner.invoke(
        app, ["check", "--scope", "hard", "--format", "json", "--path", str(repo)]
    )
    assert result.exit_code == 0, result.stdout
    data = json.loads(result.stdout)
    assert data["version"] == 1
    assert isinstance(data["findings"], list)
    assert data["summary"]["errors"] == 0


def test_check_format_json_exit_one_on_errors(
    fixture_repo: Callable[[str], Path],
) -> None:
    import json

    repo = fixture_repo("bad-frontmatter")
    result = runner.invoke(
        app, ["check", "--scope", "hard", "--format", "json", "--path", str(repo)]
    )
    assert result.exit_code == 1
    data = json.loads(result.stdout)
    assert data["summary"]["errors"] > 0
    assert any(f["check"] == "frontmatter" for f in data["findings"])


def test_check_format_json_finding_schema(
    fixture_repo: Callable[[str], Path],
) -> None:
    import json

    repo = fixture_repo("bad-frontmatter")
    result = runner.invoke(
        app, ["check", "--scope", "hard", "--format", "json", "--path", str(repo)]
    )
    data = json.loads(result.stdout)
    for finding in data["findings"]:
        assert "check" in finding
        assert "severity" in finding
        assert "message" in finding
        assert "path" in finding
        assert "doc_id" in finding
        assert "line" in finding
        assert "suggestion" in finding
        assert "category" in finding


def test_check_format_unknown_exits_two(
    fixture_repo: Callable[[str], Path],
) -> None:
    repo = fixture_repo("good")
    result = runner.invoke(app, ["check", "--format", "xml", "--path", str(repo)])
    assert result.exit_code == 2
