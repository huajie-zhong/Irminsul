"""Tests for `irminsul fix`."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from typer.testing import CliRunner

from irminsul.cli import app

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


def test_fix_advisory_profile_uses_deterministic_fixes(
    fixture_repo: Callable[[str], Path],
) -> None:
    repo = fixture_repo("soft-supersession")
    old_doc = repo / "docs" / "20-components" / "old-system.md"

    result = runner.invoke(app, ["fix", "--profile", "advisory", "--path", str(repo)])

    assert result.exit_code == 0, result.output
    text = old_doc.read_text(encoding="utf-8")
    assert "status: deprecated" in text
    assert "superseded_by: new-system" in text


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
