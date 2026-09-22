"""End-to-end tests for the brownfield baseline flow on `irminsul check`."""

from __future__ import annotations

import json
from collections.abc import Callable
from pathlib import Path

import pytest
from typer.testing import CliRunner

from irminsul.cli import app

runner = CliRunner()


def _check(repo: Path, *args: str) -> tuple[int, str]:
    result = runner.invoke(app, ["check", "--path", str(repo), *args])
    return result.exit_code, result.output


def test_baseline_flow_adopt_then_ratchet(fixture_repo: Callable[[str], Path]) -> None:
    repo = fixture_repo("bad-frontmatter")

    # Brownfield reality: the repo fails.
    code, _ = _check(repo)
    assert code == 1

    # Adopt: snapshot the debt.
    code, out = _check(repo, "--init-baseline")
    assert code == 0
    assert "baseline: recorded" in out
    assert (repo / ".irminsul-baseline.json").is_file()

    # Same violations are now hidden; CI is green.
    code, out = _check(repo)
    assert code == 0
    assert "hidden" in out

    # A NEW violation still fails, and is the only error reported.
    new_doc = repo / "docs" / "components" / "new-bad.md"
    new_doc.write_text("# No frontmatter here either\n", encoding="utf-8")
    code, out = _check(repo, "--format", "json")
    assert code == 1
    data = json.loads(out)
    assert data["baseline"]["applied"] is True
    assert data["baseline"]["suppressed"] > 0
    assert data["baseline"]["hidden"]
    error_paths = {f["path"] for f in data["findings"] if f["severity"] == "error"}
    assert error_paths == {"docs/components/new-bad.md"}


def test_github_format_reports_the_baseline_note(fixture_repo: Callable[[str], Path]) -> None:
    """The Action defaults to `--format github`, so CI must show that findings are
    hidden, both as a note and as a warning annotation on the pull request."""
    repo = fixture_repo("bad-frontmatter")
    assert _check(repo, "--init-baseline")[0] == 0

    code, out = _check(repo, "--format", "github")
    assert code == 0
    assert "hidden" in out
    assert "::warning title=irminsul baseline::" in out


def test_github_summary_lists_hidden_findings(
    fixture_repo: Callable[[str], Path], tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo = fixture_repo("bad-frontmatter")
    assert _check(repo, "--init-baseline")[0] == 0
    summary = tmp_path / "summary.md"
    monkeypatch.setenv("GITHUB_STEP_SUMMARY", str(summary))

    assert _check(repo, "--format", "github")[0] == 0

    text = summary.read_text(encoding="utf-8")
    assert "Findings hidden by the Irminsul baseline" in text
    assert "frontmatter/" in text


def test_baseline_reports_stale_entries_after_debt_paid(
    fixture_repo: Callable[[str], Path],
) -> None:
    repo = fixture_repo("bad-frontmatter")
    assert _check(repo, "--init-baseline")[0] == 0

    # Pay off one debt item entirely.
    (repo / "docs" / "components" / "bad-status.md").unlink()

    code, out = _check(repo, "--format", "json")
    assert code == 0
    data = json.loads(out)
    assert data["baseline"]["stale"] > 0

    # Ratcheting down rewrites the file smaller.
    before = len(
        json.loads((repo / ".irminsul-baseline.json").read_text(encoding="utf-8"))["findings"]
    )
    assert _check(repo, "--update-baseline")[0] == 0
    after = len(
        json.loads((repo / ".irminsul-baseline.json").read_text(encoding="utf-8"))["findings"]
    )
    assert after < before


def test_update_baseline_refuses_to_record_a_new_certain_finding(
    fixture_repo: Callable[[str], Path],
) -> None:
    repo = fixture_repo("bad-frontmatter")
    assert _check(repo, "--init-baseline")[0] == 0
    baseline = repo / ".irminsul-baseline.json"
    before = baseline.read_text(encoding="utf-8")
    (repo / "docs" / "components" / "new-bad.md").write_text("# No frontmatter\n", encoding="utf-8")

    code, out = _check(repo, "--update-baseline")

    assert code == 1
    assert "only shrinks" in out
    assert "new-bad.md" in out
    assert baseline.read_text(encoding="utf-8") == before


def test_update_baseline_needs_an_existing_baseline(fixture_repo: Callable[[str], Path]) -> None:
    repo = fixture_repo("bad-frontmatter")
    code, out = _check(repo, "--update-baseline")
    assert code == 2
    assert "--init-baseline" in out


def test_init_baseline_refuses_when_one_exists(fixture_repo: Callable[[str], Path]) -> None:
    repo = fixture_repo("bad-frontmatter")
    assert _check(repo, "--init-baseline")[0] == 0
    code, out = _check(repo, "--init-baseline")
    assert code == 2
    assert "already exists" in out


def test_no_baseline_restores_full_picture(fixture_repo: Callable[[str], Path]) -> None:
    repo = fixture_repo("bad-frontmatter")
    assert _check(repo, "--init-baseline")[0] == 0
    assert _check(repo)[0] == 0
    code, out = _check(repo, "--no-baseline", "--format", "json")
    assert code == 1
    data = json.loads(out)
    assert data["baseline"] == {
        "applied": False,
        "path": None,
        "suppressed": 0,
        "stale": 0,
        "hidden": [],
    }
    assert data["summary"]["errors"] > 0


def test_json_without_baseline_file_reports_not_applied(
    fixture_repo: Callable[[str], Path],
) -> None:
    repo = fixture_repo("bad-frontmatter")
    code, out = _check(repo, "--format", "json")
    assert code == 1
    assert json.loads(out)["baseline"]["applied"] is False


@pytest.mark.parametrize(
    "flags",
    [
        ("--update-baseline", "--no-baseline"),
        ("--init-baseline", "--update-baseline"),
        ("--init-baseline", "--delta"),
    ],
)
def test_baseline_flags_are_mutually_exclusive(
    fixture_repo: Callable[[str], Path], flags: tuple[str, str]
) -> None:
    repo = fixture_repo("bad-frontmatter")
    code, out = _check(repo, *flags)
    assert code == 2
    assert "mutually exclusive" in out


def test_corrupt_baseline_fails_loudly(fixture_repo: Callable[[str], Path]) -> None:
    repo = fixture_repo("bad-frontmatter")
    (repo / ".irminsul-baseline.json").write_text("not json", encoding="utf-8")
    code, out = _check(repo)
    assert code == 2
    assert "baseline" in out


def test_list_baseline_shows_hidden_and_fixed_entries(
    fixture_repo: Callable[[str], Path],
) -> None:
    repo = fixture_repo("bad-frontmatter")
    assert _check(repo, "--init-baseline")[0] == 0
    (repo / "docs" / "components" / "bad-status.md").unlink()

    result = runner.invoke(app, ["list", "baseline", "--format", "json", "--path", str(repo)])

    assert result.exit_code == 0, result.output
    rows = json.loads(result.output)["entries"]
    states = {row["path"]: row["state"] for row in rows}
    assert states["docs/components/bad-status.md"] == "fixed"
    assert "hidden" in states.values()

    plain = runner.invoke(app, ["list", "baseline", "--path", str(repo)])
    assert "run irminsul check --update-baseline" in plain.output


def test_only_certain_findings_are_baselined(fixture_repo: Callable[[str], Path]) -> None:
    repo = fixture_repo("good")
    doc = repo / "docs" / "components" / "composer.md"
    doc.write_text(
        doc.read_text(encoding="utf-8")
        + "\nBatching is planned.\n"
        + '\n<!-- irminsul:ignore prose-file-reference reason="paid debt" -->\n',
        encoding="utf-8",
    )

    assert _check(repo, "--init-baseline")[0] == 0
    baseline = json.loads((repo / ".irminsul-baseline.json").read_text(encoding="utf-8"))
    assert baseline["findings"] == []

    code, out = _check(repo, "--format", "json")
    assert code == 1
    codes = {finding["code"] for finding in json.loads(out)["findings"]}
    assert {"prose-file-reference/stale-suppression", "reality/speculative-language"} <= codes
