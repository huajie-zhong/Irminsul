"""Tests for `irminsul fix`."""

from __future__ import annotations

import json
from collections.abc import Callable
from pathlib import Path

from typer.testing import CliRunner

from irminsul.checks.base import Fix
from irminsul.cli import app
from irminsul.fix import apply_fixes

runner = CliRunner()


def test_fix_rejects_removed_scope() -> None:
    result = runner.invoke(app, ["fix", "--scope", "soft"])
    assert result.exit_code != 0


def test_fix_supersession_dry_run_does_not_write(fixture_repo: Callable[[str], Path]) -> None:
    repo = fixture_repo("soft-supersession")
    old_doc = repo / "docs" / "20-components" / "old-system.md"
    before = old_doc.read_text(encoding="utf-8")

    result = runner.invoke(app, ["fix", "--dry-run", "--path", str(repo)])

    assert result.exit_code == 0, result.output
    assert "status: deprecated" in result.output
    assert old_doc.read_text(encoding="utf-8") == before


def test_fix_hard_profile_does_not_apply_soft_fixes(fixture_repo: Callable[[str], Path]) -> None:
    repo = fixture_repo("soft-supersession")
    old_doc = repo / "docs" / "20-components" / "old-system.md"
    before = old_doc.read_text(encoding="utf-8")

    result = runner.invoke(app, ["fix", "--profile", "hard", "--path", str(repo)])

    assert result.exit_code == 0, result.output
    assert "no automatic fixes available" in result.output
    assert old_doc.read_text(encoding="utf-8") == before


def test_fix_rejects_removed_advisory_profile(
    fixture_repo: Callable[[str], Path],
) -> None:
    """The advisory profile died with the LLM check subsystem."""
    repo = fixture_repo("soft-supersession")
    old_doc = repo / "docs" / "20-components" / "old-system.md"
    before = old_doc.read_text(encoding="utf-8")

    result = runner.invoke(app, ["fix", "--profile", "advisory", "--path", str(repo)])

    assert result.exit_code != 0
    assert "Invalid value" in result.output
    assert old_doc.read_text(encoding="utf-8") == before


def test_fix_all_available_uses_unconfigured_deterministic_fixes(
    fixture_repo: Callable[[str], Path],
) -> None:
    repo = fixture_repo("soft-supersession")
    (repo / "irminsul.toml").write_text(
        'project_name = "soft-supersession-fixture"\n'
        "[paths]\n"
        'docs_root = "docs"\n'
        'source_roots = ["app"]\n',
        encoding="utf-8",
    )
    old_doc = repo / "docs" / "20-components" / "old-system.md"

    result = runner.invoke(app, ["fix", "--profile", "all-available", "--path", str(repo)])

    assert result.exit_code == 0, result.output
    text = old_doc.read_text(encoding="utf-8")
    assert "status: deprecated" in text
    assert "superseded_by: new-system" in text


def test_fix_supersession_writes_frontmatter(fixture_repo: Callable[[str], Path]) -> None:
    repo = fixture_repo("soft-supersession")
    old_doc = repo / "docs" / "20-components" / "old-system.md"

    result = runner.invoke(app, ["fix", "--path", str(repo)])

    assert result.exit_code == 0, result.output
    text = old_doc.read_text(encoding="utf-8")
    assert "status: deprecated" in text
    assert "superseded_by: new-system" in text


def test_fix_holds_confirm_required_fixes_without_confirm(
    fixture_repo: Callable[[str], Path],
) -> None:
    repo = fixture_repo("soft-rfc-resolution")
    rfc = repo / "docs" / "80-evolution" / "rfcs" / "0002-accepted-bad-status.md"
    before = rfc.read_text(encoding="utf-8")

    result = runner.invoke(app, ["fix", "--profile", "configured", "--path", str(repo)])

    assert result.exit_code == 0, result.output
    assert "held" in result.output
    assert "--confirm" in result.output
    assert rfc.read_text(encoding="utf-8") == before


def test_fix_confirm_applies_irreversible_fixes(
    fixture_repo: Callable[[str], Path],
) -> None:
    repo = fixture_repo("soft-rfc-resolution")
    rfc = repo / "docs" / "80-evolution" / "rfcs" / "0002-accepted-bad-status.md"

    result = runner.invoke(
        app, ["fix", "--profile", "configured", "--confirm", "--path", str(repo)]
    )

    assert result.exit_code == 0, result.output
    assert "status: stable" in rfc.read_text(encoding="utf-8")


def test_fix_check_selector_applies_named_check(
    fixture_repo: Callable[[str], Path],
) -> None:
    repo = fixture_repo("soft-supersession")
    old_doc = repo / "docs" / "20-components" / "old-system.md"

    result = runner.invoke(app, ["fix", "--check", "supersession", "--path", str(repo)])

    assert result.exit_code == 0, result.output
    assert "status: deprecated" in old_doc.read_text(encoding="utf-8")


def test_apply_fixes_excludes_noop_fix_from_written(tmp_path: Path) -> None:
    """A planned fix that changes nothing must not be reported as written."""
    (tmp_path / "changed.md").write_text("before\n", encoding="utf-8")
    (tmp_path / "untouched.md").write_text("stable\n", encoding="utf-8")

    fixes = [
        Fix(Path("changed.md"), "rewrite the body", lambda text: "after\n"),
        Fix(Path("untouched.md"), "no-op rewrite", lambda text: text),
    ]

    result = apply_fixes(tmp_path, fixes, dry_run=False)

    assert len(result.planned) == 2
    assert result.written == [Path("changed.md")]
    assert result.errors == []


def test_fix_live_run_lists_written_files_only(fixture_repo: Callable[[str], Path]) -> None:
    repo = fixture_repo("soft-supersession")

    result = runner.invoke(app, ["fix", "--format", "json", "--path", str(repo)])

    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert payload["version"] == 1
    assert payload["dry_run"] is False
    assert payload["written"] == ["docs/20-components/old-system.md"]
    assert payload["errors"] == []
    # Two fixes target the same doc and group into one write, so `planned` is not
    # a per-file list and cannot stand in for what changed.
    assert len(payload["planned"]) == 2
    assert {entry["path"] for entry in payload["planned"]} == {"docs/20-components/old-system.md"}


def test_fix_dry_run_json_reports_plan_without_writing(
    fixture_repo: Callable[[str], Path],
) -> None:
    repo = fixture_repo("soft-supersession")
    old_doc = repo / "docs" / "20-components" / "old-system.md"
    before = old_doc.read_text(encoding="utf-8")

    result = runner.invoke(app, ["fix", "--dry-run", "--format", "json", "--path", str(repo)])

    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert payload["dry_run"] is True
    assert payload["written"] == []
    assert payload["planned"]
    assert old_doc.read_text(encoding="utf-8") == before


def test_fix_json_reports_held_fixes(fixture_repo: Callable[[str], Path]) -> None:
    repo = fixture_repo("soft-rfc-resolution")

    result = runner.invoke(
        app, ["fix", "--profile", "configured", "--format", "json", "--path", str(repo)]
    )

    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert payload["held"]
    assert all({"path", "description"} == set(entry) for entry in payload["held"])


def test_fix_json_is_emitted_when_nothing_is_harvested(
    fixture_repo: Callable[[str], Path],
) -> None:
    repo = fixture_repo("good")

    result = runner.invoke(app, ["fix", "--format", "json", "--path", str(repo)])

    assert result.exit_code == 0, result.output
    assert json.loads(result.output) == {
        "version": 1,
        "dry_run": False,
        "written": [],
        "planned": [],
        "held": [],
        "errors": [],
        "notes": ["no automatic fixes available"],
    }


def test_fix_rejects_unknown_format(fixture_repo: Callable[[str], Path]) -> None:
    repo = fixture_repo("soft-supersession")

    result = runner.invoke(app, ["fix", "--format", "yaml", "--path", str(repo)])

    assert result.exit_code == 2
    assert "unknown --format" in result.output


def test_fix_check_selector_inactive_name_is_noop(
    fixture_repo: Callable[[str], Path],
) -> None:
    repo = fixture_repo("soft-supersession")
    old_doc = repo / "docs" / "20-components" / "old-system.md"
    before = old_doc.read_text(encoding="utf-8")

    result = runner.invoke(
        app,
        ["fix", "--check", "rfc-resolution", "--profile", "configured", "--path", str(repo)],
    )

    assert result.exit_code == 0, result.output
    assert "not active" in result.output
    assert old_doc.read_text(encoding="utf-8") == before

    # The JSON envelope used to be byte-identical to a genuine nothing-to-fix
    # run, so an agent following a stale hint read the finding as resolved.
    result = runner.invoke(
        app,
        [
            "fix",
            "--check",
            "rfc-resolution",
            "--profile",
            "configured",
            "--format",
            "json",
            "--path",
            str(repo),
        ],
    )
    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert payload["written"] == [] and payload["planned"] == []
    assert payload["notes"] == ["check 'rfc-resolution' is not active under profile 'configured'"]


def test_fix_supersession_handles_crlf_and_closing_delimiter_at_eof(
    fixture_repo: Callable[[str], Path],
) -> None:
    repo = fixture_repo("soft-supersession")
    old_doc = repo / "docs" / "20-components" / "old-system.md"
    old_doc.write_text(
        "---\r\n"
        "id: old-system\r\n"
        "title: Old System\r\n"
        "audience: explanation\r\n"
        "tier: 3\r\n"
        "status: stable\r\n"
        "---",
        encoding="utf-8",
    )

    result = runner.invoke(app, ["fix", "--path", str(repo)])

    assert result.exit_code == 0, result.output
    text = old_doc.read_text(encoding="utf-8")
    assert "status: deprecated" in text
    assert "superseded_by: new-system" in text
