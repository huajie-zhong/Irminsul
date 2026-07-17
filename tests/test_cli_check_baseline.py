"""End-to-end tests for the brownfield baseline flow on `irminsul check`."""

from __future__ import annotations

import json
from collections.abc import Callable
from pathlib import Path

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
    code, out = _check(repo, "--update-baseline")
    assert code == 0
    assert "baseline: wrote" in out
    assert (repo / ".irminsul-baseline.json").is_file()

    # Same violations are now suppressed; CI is green.
    code, out = _check(repo)
    assert code == 0
    assert "suppressed" in out

    # A NEW violation still fails, and is the only error reported.
    new_doc = repo / "docs" / "20-components" / "new-bad.md"
    new_doc.write_text("# No frontmatter here either\n", encoding="utf-8")
    code, out = _check(repo, "--format", "json")
    assert code == 1
    data = json.loads(out)
    assert data["baseline"]["applied"] is True
    assert data["baseline"]["suppressed"] > 0
    error_paths = {f["path"] for f in data["findings"] if f["severity"] == "error"}
    assert error_paths == {"docs/20-components/new-bad.md"}


def test_baseline_reports_stale_entries_after_debt_paid(
    fixture_repo: Callable[[str], Path],
) -> None:
    repo = fixture_repo("bad-frontmatter")
    assert _check(repo, "--update-baseline")[0] == 0

    # Pay off one debt item entirely.
    (repo / "docs" / "20-components" / "bad-tier.md").unlink()

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


def test_no_baseline_restores_full_picture(fixture_repo: Callable[[str], Path]) -> None:
    repo = fixture_repo("bad-frontmatter")
    assert _check(repo, "--update-baseline")[0] == 0
    assert _check(repo)[0] == 0
    code, out = _check(repo, "--no-baseline", "--format", "json")
    assert code == 1
    data = json.loads(out)
    assert data["baseline"] == {"applied": False, "path": None, "suppressed": 0, "stale": 0}
    assert data["summary"]["errors"] > 0


def test_json_without_baseline_file_reports_not_applied(
    fixture_repo: Callable[[str], Path],
) -> None:
    repo = fixture_repo("bad-frontmatter")
    code, out = _check(repo, "--format", "json")
    assert code == 1
    assert json.loads(out)["baseline"]["applied"] is False


def test_update_baseline_conflicts_with_no_baseline(
    fixture_repo: Callable[[str], Path],
) -> None:
    repo = fixture_repo("bad-frontmatter")
    code, out = _check(repo, "--update-baseline", "--no-baseline")
    assert code == 2
    assert "mutually exclusive" in out


def test_corrupt_baseline_fails_loudly(fixture_repo: Callable[[str], Path]) -> None:
    repo = fixture_repo("bad-frontmatter")
    (repo / ".irminsul-baseline.json").write_text("not json", encoding="utf-8")
    code, out = _check(repo)
    assert code == 2
    assert "baseline" in out


def test_stale_suppression_info_cannot_be_baselined(
    fixture_repo: Callable[[str], Path],
) -> None:
    repo = fixture_repo("good")
    doc = repo / "docs" / "20-components" / "composer.md"
    doc.write_text(
        doc.read_text(encoding="utf-8")
        + '\n<!-- irminsul:ignore prose-file-reference reason="paid debt" -->\n',
        encoding="utf-8",
    )

    assert _check(repo, "--update-baseline")[0] == 0
    baseline = json.loads((repo / ".irminsul-baseline.json").read_text(encoding="utf-8"))
    assert all(
        finding["message"]
        != "line suppression no longer hides an unlinked local Markdown reference"
        for finding in baseline["findings"]
    )

    code, out = _check(repo, "--format", "json")
    assert code == 0
    data = json.loads(out)
    assert any(
        finding["data"] == {"problem": "stale-suppression", "scope": "line"}
        for finding in data["findings"]
    )
