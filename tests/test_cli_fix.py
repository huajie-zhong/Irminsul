"""Tests for `irminsul fix`."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from typer.testing import CliRunner

from irminsul.cli import app

runner = CliRunner()


def test_fix_supersession_dry_run_does_not_write(fixture_repo: Callable[[str], Path]) -> None:
    repo = fixture_repo("soft-supersession")
    old_doc = repo / "docs" / "20-components" / "old-system.md"
    before = old_doc.read_text(encoding="utf-8")

    result = runner.invoke(app, ["fix", "--dry-run", "--path", str(repo)])

    assert result.exit_code == 0, result.output
    assert "status: deprecated" in result.output
    assert old_doc.read_text(encoding="utf-8") == before


def test_fix_supersession_writes_frontmatter(fixture_repo: Callable[[str], Path]) -> None:
    repo = fixture_repo("soft-supersession")
    old_doc = repo / "docs" / "20-components" / "old-system.md"

    result = runner.invoke(app, ["fix", "--path", str(repo)])

    assert result.exit_code == 0, result.output
    text = old_doc.read_text(encoding="utf-8")
    assert "status: deprecated" in text
    assert "superseded_by: new-system" in text
