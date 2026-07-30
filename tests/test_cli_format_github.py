"""Tests for `irminsul check --format github` workflow-command output."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from typer.testing import CliRunner

from irminsul.checks.base import Finding, Severity
from irminsul.cli import _github_annotation, app

runner = CliRunner()


def test_annotation_full_shape() -> None:
    finding = Finding(
        check="frontmatter",
        code="frontmatter/missing-field",
        severity=Severity.error,
        message="missing field",
        path=Path("docs/a.md"),
        line=3,
        suggestion="add it",
    )
    assert _github_annotation(finding) == (
        "::error file=docs/a.md,line=3,title=irminsul frontmatter,"
        "code=frontmatter/missing-field::missing field — add it"
    )


def test_annotation_severity_mapping() -> None:
    for severity, command in [
        (Severity.error, "::error"),
        (Severity.warning, "::warning"),
        (Severity.info, "::notice"),
    ]:
        finding = Finding(
            check="x", code="x/y", severity=severity, message="m", path=Path("docs/a.md")
        )
        assert _github_annotation(finding).startswith(f"{command} ")


def test_annotation_omits_line_when_none() -> None:
    finding = Finding(
        check="x", code="x/y", severity=Severity.error, message="m", path=Path("docs/a.md")
    )
    assert _github_annotation(finding) == ("::error file=docs/a.md,title=irminsul x,code=x/y::m")


def test_annotation_omits_file_when_path_none() -> None:
    finding = Finding(check="x", code="x/y", severity=Severity.warning, message="m")
    assert _github_annotation(finding) == "::warning title=irminsul x,code=x/y::m"


def test_annotation_escapes_message_data() -> None:
    finding = Finding(
        check="x",
        code="x/y",
        severity=Severity.info,
        message="50% done\r\nnext line",
    )
    assert _github_annotation(finding) == (
        "::notice title=irminsul x,code=x/y::50%25 done%0D%0Anext line"
    )


def test_annotation_escapes_property_values() -> None:
    finding = Finding(
        check="x",
        code="x/y",
        severity=Severity.error,
        message="m",
        path=Path("docs/a,b:c.md"),
    )
    assert _github_annotation(finding) == (
        "::error file=docs/a%2Cb%3Ac.md,title=irminsul x,code=x/y::m"
    )


def test_annotation_no_suggestion_separator_without_suggestion() -> None:
    finding = Finding(
        check="x", code="x/y", severity=Severity.error, message="m", path=Path("docs/a.md")
    )
    assert "—" not in _github_annotation(finding)


def test_check_format_github_end_to_end(fixture_repo: Callable[[str], Path]) -> None:
    repo = fixture_repo("bad-frontmatter")
    result = runner.invoke(
        app, ["check", "--profile", "hard", "--format", "github", "--path", str(repo)]
    )
    assert result.exit_code == 1
    lines = result.stdout.splitlines()
    annotations = [line for line in lines if line.startswith("::")]
    assert annotations, result.stdout
    assert all(line.startswith(("::error ", "::warning ", "::notice ")) for line in annotations)
    assert any("title=irminsul " in line for line in annotations)
    # the plain one-line summary still closes the output
    assert "error" in lines[-1] and "warning" in lines[-1]


def test_check_format_github_green_repo_prints_summary_only(
    fixture_repo: Callable[[str], Path],
) -> None:
    repo = fixture_repo("good")
    result = runner.invoke(
        app, ["check", "--profile", "hard", "--format", "github", "--path", str(repo)]
    )
    assert result.exit_code == 0
    assert not [line for line in result.stdout.splitlines() if line.startswith("::")]
    assert "0 errors, 0 warnings" in result.stdout


def test_check_rejects_unknown_format(fixture_repo: Callable[[str], Path]) -> None:
    repo = fixture_repo("good")
    result = runner.invoke(app, ["check", "--format", "sarif", "--path", str(repo)])
    assert result.exit_code == 2
    assert "plain, json, or github" in result.stdout
