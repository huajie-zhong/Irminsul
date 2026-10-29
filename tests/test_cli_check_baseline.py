"""End-to-end tests for the brownfield baseline flow on `irminsul check`."""

from __future__ import annotations

import json
from collections.abc import Callable
from pathlib import Path

import pytest
from typer.testing import CliRunner

from irminsul.cli import app

from .conftest import invoke

runner = CliRunner()


def test_baseline_flow_adopt_then_ratchet(fixture_repo: Callable[[str], Path]) -> None:
    repo = fixture_repo("bad-frontmatter")

    # Brownfield reality: the repo fails.
    code, _ = invoke(repo, "check")
    assert code == 1

    # Adopt: snapshot the debt.
    code, out = invoke(repo, "baseline", "init")
    assert code == 0
    assert "baseline: recorded" in out
    assert (repo / ".irminsul-baseline.json").is_file()

    # Same violations are now hidden; CI is green.
    code, out = invoke(repo, "check")
    assert code == 0
    assert "hidden" in out

    # A NEW violation still fails, and is the only error reported.
    new_doc = repo / "docs" / "components" / "new-bad.md"
    new_doc.write_text("# No frontmatter here either\n", encoding="utf-8")
    code, out = invoke(repo, "check", "--format", "json")
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
    assert invoke(repo, "baseline", "init")[0] == 0

    code, out = invoke(repo, "check", "--format", "github")
    assert code == 0
    assert "hidden" in out
    assert "::warning title=irminsul baseline::" in out


def test_github_summary_lists_hidden_findings(
    fixture_repo: Callable[[str], Path], tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo = fixture_repo("bad-frontmatter")
    assert invoke(repo, "baseline", "init")[0] == 0
    summary = tmp_path / "summary.md"
    monkeypatch.setenv("GITHUB_STEP_SUMMARY", str(summary))

    assert invoke(repo, "check", "--format", "github")[0] == 0

    text = summary.read_text(encoding="utf-8")
    assert "Findings hidden by the Irminsul baseline" in text
    assert "frontmatter/" in text


def test_baseline_reports_stale_entries_after_debt_paid(
    fixture_repo: Callable[[str], Path],
) -> None:
    repo = fixture_repo("bad-frontmatter")
    assert invoke(repo, "baseline", "init")[0] == 0

    # Pay off one debt item entirely.
    (repo / "docs" / "components" / "bad-status.md").unlink()

    code, out = invoke(repo, "check", "--format", "json")
    assert code == 0
    data = json.loads(out)
    assert data["baseline"]["stale"] > 0

    # Ratcheting down rewrites the file smaller.
    before = len(
        json.loads((repo / ".irminsul-baseline.json").read_text(encoding="utf-8"))["findings"]
    )
    assert invoke(repo, "baseline", "update")[0] == 0
    after = len(
        json.loads((repo / ".irminsul-baseline.json").read_text(encoding="utf-8"))["findings"]
    )
    assert after < before


def test_only_counts_the_stale_entries_of_the_checks_it_ran(
    fixture_repo: Callable[[str], Path],
) -> None:
    repo = fixture_repo("bad-frontmatter")
    assert invoke(repo, "baseline", "init")[0] == 0
    (repo / "docs" / "components" / "bad-status.md").unlink()

    out = invoke(repo, "check", "--only", "links", "--format", "json")[1]
    assert json.loads(out)["baseline"]["stale"] == 0
    assert "fixed entr" not in invoke(repo, "check", "--only", "links")[1]

    out = invoke(repo, "check", "--only", "frontmatter", "--format", "json")[1]
    assert json.loads(out)["baseline"]["stale"] > 0


def test_an_entry_no_registered_check_can_match_is_stale_whatever_ran(
    fixture_repo: Callable[[str], Path],
) -> None:
    repo = fixture_repo("bad-frontmatter")
    assert invoke(repo, "baseline", "init")[0] == 0
    baseline = repo / ".irminsul-baseline.json"
    payload = json.loads(baseline.read_text(encoding="utf-8"))
    payload["findings"].append({"check": "history-depth", "path": ".", "message": "by hand"})
    baseline.write_text(json.dumps(payload), encoding="utf-8")

    out = invoke(repo, "check", "--only", "links", "--format", "json")[1]

    assert json.loads(out)["baseline"]["stale"] == 1


def test_baseline_update_keeps_the_entries_of_every_enabled_check(
    fixture_repo: Callable[[str], Path],
) -> None:
    repo = fixture_repo("bad-frontmatter")
    assert invoke(repo, "baseline", "init")[0] == 0
    baseline = repo / ".irminsul-baseline.json"
    before = baseline.read_text(encoding="utf-8")

    code, out = invoke(repo, "baseline", "update")

    assert code == 0
    assert "removed 0 fixed entries" in out
    assert baseline.read_text(encoding="utf-8") == before


def test_update_baseline_refuses_to_record_a_new_certain_finding(
    fixture_repo: Callable[[str], Path],
) -> None:
    repo = fixture_repo("bad-frontmatter")
    assert invoke(repo, "baseline", "init")[0] == 0
    baseline = repo / ".irminsul-baseline.json"
    before = baseline.read_text(encoding="utf-8")
    (repo / "docs" / "components" / "new-bad.md").write_text("# No frontmatter\n", encoding="utf-8")

    code, out = invoke(repo, "baseline", "update")

    assert code == 1
    assert "only shrinks" in out
    assert "new-bad.md" in out
    assert baseline.read_text(encoding="utf-8") == before


def test_update_baseline_needs_an_existing_baseline(fixture_repo: Callable[[str], Path]) -> None:
    repo = fixture_repo("bad-frontmatter")
    code, out = invoke(repo, "baseline", "update")
    assert code == 2
    assert "irminsul baseline init" in out


def test_init_baseline_refuses_when_one_exists(fixture_repo: Callable[[str], Path]) -> None:
    repo = fixture_repo("bad-frontmatter")
    assert invoke(repo, "baseline", "init")[0] == 0
    code, out = invoke(repo, "baseline", "init")
    assert code == 1
    assert "already exists" in out


def test_no_baseline_restores_full_picture(fixture_repo: Callable[[str], Path]) -> None:
    repo = fixture_repo("bad-frontmatter")
    assert invoke(repo, "baseline", "init")[0] == 0
    assert invoke(repo, "check")[0] == 0
    code, out = invoke(repo, "check", "--no-baseline", "--format", "json")
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
    code, out = invoke(repo, "check", "--format", "json")
    assert code == 1
    assert json.loads(out)["baseline"]["applied"] is False


def test_corrupt_baseline_fails_loudly(fixture_repo: Callable[[str], Path]) -> None:
    repo = fixture_repo("bad-frontmatter")
    (repo / ".irminsul-baseline.json").write_text("not json", encoding="utf-8")
    code, out = invoke(repo, "check")
    assert code == 2
    assert "baseline" in out


def test_list_baseline_shows_hidden_and_fixed_entries(
    fixture_repo: Callable[[str], Path],
) -> None:
    repo = fixture_repo("bad-frontmatter")
    assert invoke(repo, "baseline", "init")[0] == 0
    (repo / "docs" / "components" / "bad-status.md").unlink()

    result = runner.invoke(app, ["list", "baseline", "--format", "json", "--path", str(repo)])

    assert result.exit_code == 0, result.output
    rows = json.loads(result.output)["entries"]
    states = {row["path"]: row["state"] for row in rows}
    assert states["docs/components/bad-status.md"] == "fixed"
    assert "hidden" in states.values()

    plain = runner.invoke(app, ["list", "baseline", "--path", str(repo)])
    assert "run irminsul baseline update" in plain.output


def test_only_certain_findings_are_baselined(fixture_repo: Callable[[str], Path]) -> None:
    repo = fixture_repo("good")
    doc = repo / "docs" / "components" / "composer.md"
    doc.write_text(
        doc.read_text(encoding="utf-8")
        + "\nBatching runs through `batch_all()`.\n"
        + '\n<!-- irminsul:ignore code-references reason="paid debt" -->\n',
        encoding="utf-8",
    )

    assert invoke(repo, "baseline", "init")[0] == 0
    baseline = json.loads((repo / ".irminsul-baseline.json").read_text(encoding="utf-8"))
    assert baseline["findings"] == []

    code, out = invoke(repo, "check", "--format", "json")
    assert code == 1
    codes = {finding["code"] for finding in json.loads(out)["findings"]}
    assert {"ignore-comment/unused", "code-references/unknown-symbol"} <= codes
