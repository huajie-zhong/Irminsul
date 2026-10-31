"""Tests for `irminsul fix`."""

from __future__ import annotations

import json
import os
from collections.abc import Callable
from pathlib import Path

import pytest
from typer.testing import CliRunner

from irminsul.checks.base import Fix
from irminsul.cli import app
from irminsul.fix import FixResult, apply_fixes

from .conftest import write_config

runner = CliRunner()


def test_fix_supersession_dry_run_does_not_write(fixture_repo: Callable[[str], Path]) -> None:
    repo = fixture_repo("soft-supersession")
    old_doc = repo / "docs" / "components" / "old-system.md"
    before = old_doc.read_text(encoding="utf-8")

    result = runner.invoke(app, ["fix", "--dry-run", "--path", str(repo)])

    assert result.exit_code == 0, result.output
    assert "held 1 fix(es)" in result.output
    assert "status: deprecated" not in result.output
    assert old_doc.read_text(encoding="utf-8") == before


def test_fix_skips_checks_that_are_not_enabled(fixture_repo: Callable[[str], Path]) -> None:
    repo = fixture_repo("soft-supersession")
    write_config(
        repo,
        project_name="soft-supersession-fixture",
        source_roots=["app"],
        enabled=["frontmatter"],
    )
    old_doc = repo / "docs" / "components" / "old-system.md"
    before = old_doc.read_text(encoding="utf-8")

    result = runner.invoke(app, ["fix", "--path", str(repo)])

    assert result.exit_code == 0, result.output
    assert "no automatic fixes available" in result.output
    assert old_doc.read_text(encoding="utf-8") == before


def test_fix_only_harvests_a_check_that_is_not_enabled(
    fixture_repo: Callable[[str], Path],
) -> None:
    repo = fixture_repo("soft-supersession")
    write_config(repo, project_name="soft-supersession-fixture", source_roots=["app"])
    old_doc = repo / "docs" / "components" / "old-system.md"

    result = runner.invoke(app, ["fix", "--only", "supersession", "--confirm", "--path", str(repo)])

    assert result.exit_code == 0, result.output
    assert "\nstatus: deprecated\n" in old_doc.read_text(encoding="utf-8")


def test_fix_supersession_deprecates_only_with_confirm(
    fixture_repo: Callable[[str], Path],
) -> None:
    repo = fixture_repo("soft-supersession")
    old_doc = repo / "docs" / "components" / "old-system.md"
    before = old_doc.read_text(encoding="utf-8")

    held = runner.invoke(app, ["fix", "--path", str(repo)])
    assert held.exit_code == 0, held.output
    assert "--confirm" in held.output
    assert old_doc.read_text(encoding="utf-8") == before

    result = runner.invoke(app, ["fix", "--confirm", "--path", str(repo)])

    assert result.exit_code == 0, result.output
    text = old_doc.read_text(encoding="utf-8")
    assert "\nstatus: deprecated\n" in text
    assert "superseded_by" not in text


def test_fix_holds_confirm_required_fixes_without_confirm(
    fixture_repo: Callable[[str], Path],
) -> None:
    repo = fixture_repo("soft-rfc-follow-through")
    rfc = repo / "docs" / "rfcs" / "0002-accepted-bad-status.md"
    before = rfc.read_text(encoding="utf-8")

    result = runner.invoke(app, ["fix", "--path", str(repo)])

    assert result.exit_code == 0, result.output
    assert "held" in result.output
    assert "--confirm" in result.output
    assert rfc.read_text(encoding="utf-8") == before


def test_fix_confirm_applies_irreversible_fixes(
    fixture_repo: Callable[[str], Path],
) -> None:
    repo = fixture_repo("soft-rfc-follow-through")
    rfc = repo / "docs" / "rfcs" / "0002-accepted-bad-status.md"

    result = runner.invoke(app, ["fix", "--confirm", "--path", str(repo)])

    assert result.exit_code == 0, result.output
    assert "status: stable" in rfc.read_text(encoding="utf-8")


def test_fix_only_applies_the_named_check(
    fixture_repo: Callable[[str], Path],
) -> None:
    repo = fixture_repo("soft-supersession")
    old_doc = repo / "docs" / "components" / "old-system.md"

    result = runner.invoke(app, ["fix", "--only", "supersession", "--confirm", "--path", str(repo)])

    assert result.exit_code == 0, result.output
    assert "status: deprecated" in old_doc.read_text(encoding="utf-8").split("---")[1]


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


def test_apply_fixes_writes_each_file_with_the_line_endings_it_had(tmp_path: Path) -> None:
    (tmp_path / "crlf.md").write_bytes(b"one\r\ntwo\r\n")
    (tmp_path / "lf.md").write_bytes(b"one\ntwo\n")
    fixes = [
        Fix(Path(name), "append a line", lambda text: text + "three\n")
        for name in ("crlf.md", "lf.md")
    ]

    result = apply_fixes(tmp_path, fixes, dry_run=False)

    assert result.errors == []
    assert (tmp_path / "crlf.md").read_bytes() == b"one\r\ntwo\r\nthree\r\n"
    assert (tmp_path / "lf.md").read_bytes() == b"one\ntwo\nthree\n"


def test_apply_fixes_leaves_a_neighbouring_tmp_file_alone(tmp_path: Path) -> None:
    (tmp_path / "doc.md").write_text("before\n", encoding="utf-8")
    (tmp_path / "doc.md.tmp").write_text("somebody's file\n", encoding="utf-8")

    result = apply_fixes(
        tmp_path, [Fix(Path("doc.md"), "rewrite", lambda text: "after\n")], dry_run=False
    )

    assert result.errors == []
    assert (tmp_path / "doc.md").read_text(encoding="utf-8") == "after\n"
    assert (tmp_path / "doc.md.tmp").read_text(encoding="utf-8") == "somebody's file\n"


def test_a_failed_replace_leaves_the_file_and_no_temporary(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    (tmp_path / "doc.md").write_text("before\n", encoding="utf-8")

    def refuse(src: object, dst: object) -> None:
        raise PermissionError("locked")

    monkeypatch.setattr(os, "replace", refuse)

    result = apply_fixes(
        tmp_path, [Fix(Path("doc.md"), "rewrite", lambda text: "after\n")], dry_run=False
    )

    assert result.written == []
    assert [error.split(":")[0] for error in result.errors] == ["doc.md"]
    assert sorted(path.name for path in tmp_path.iterdir()) == ["doc.md"]
    assert (tmp_path / "doc.md").read_text(encoding="utf-8") == "before\n"


def test_fix_live_run_lists_written_files_only(fixture_repo: Callable[[str], Path]) -> None:
    repo = fixture_repo("soft-supersession")
    (repo / "docs" / "components" / "newest-system.md").write_text(
        "---\nid: newest-system\ntitle: Newest System\nstatus: stable\n"
        "supersedes: [old-system]\n---\n\n# Newest System\n\nAlso replaces it.\n",
        encoding="utf-8",
    )

    result = runner.invoke(app, ["fix", "--confirm", "--format", "json", "--path", str(repo)])

    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert payload["version"] == 1
    assert payload["dry_run"] is False
    assert payload["written"] == ["docs/components/old-system.md"]
    assert payload["errors"] == []
    # Two fixes target the same doc and group into one write, so `planned` is not
    # a per-file list and cannot stand in for what changed.
    assert len(payload["planned"]) == 2
    assert {entry["path"] for entry in payload["planned"]} == {"docs/components/old-system.md"}


def test_fix_dry_run_json_reports_plan_without_writing(
    fixture_repo: Callable[[str], Path],
) -> None:
    repo = fixture_repo("soft-supersession")
    old_doc = repo / "docs" / "components" / "old-system.md"
    before = old_doc.read_text(encoding="utf-8")

    result = runner.invoke(
        app, ["fix", "--dry-run", "--confirm", "--format", "json", "--path", str(repo)]
    )

    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert payload["dry_run"] is True
    assert payload["written"] == []
    assert payload["planned"]
    assert old_doc.read_text(encoding="utf-8") == before


def test_fix_json_reports_held_fixes(fixture_repo: Callable[[str], Path]) -> None:
    repo = fixture_repo("soft-rfc-follow-through")

    result = runner.invoke(app, ["fix", "--format", "json", "--path", str(repo)])

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


def test_fix_supersession_handles_crlf_and_closing_delimiter_at_eof(
    fixture_repo: Callable[[str], Path],
) -> None:
    repo = fixture_repo("soft-supersession")
    old_doc = repo / "docs" / "components" / "old-system.md"
    old_doc.write_text(
        "---\r\n"
        "id: old-system\r\n"
        "title: Old System\r\n"
        "audience: explanation\r\n"
        "status: stable\r\n"
        "---",
        encoding="utf-8",
    )

    result = runner.invoke(app, ["fix", "--confirm", "--path", str(repo)])

    assert result.exit_code == 0, result.output
    assert "status: deprecated" in old_doc.read_text(encoding="utf-8")


def test_fix_only_rejects_an_unknown_name(
    fixture_repo: Callable[[str], Path],
) -> None:
    """A typo must exit rather than harvest nothing, which reads as nothing to fix."""
    repo = fixture_repo("soft-supersession")

    result = runner.invoke(
        app,
        ["fix", "--only", "glossary-disipline", "--format", "json", "--path", str(repo)],
    )

    assert result.exit_code == 2, result.output
    assert "unknown check name(s): 'glossary-disipline'" in result.output
    assert "did you mean 'glossary-discipline'" in result.output


_HELD_SUMMARY = "held 1 fix(es): --dry-run --confirm lists them, --confirm applies them"
_HELD_RFC = "docs/rfcs/0002-accepted-bad-status.md"


def _planned_and_held_repo(fixture_repo: Callable[[str], Path]) -> Path:
    """A repository with two fixes that run by default and one that waits for `--confirm`."""
    repo = fixture_repo("soft-lifecycle")
    held = fixture_repo("soft-rfc-follow-through") / _HELD_RFC
    (repo / "docs" / "rfcs" / held.name).write_text(
        held.read_text(encoding="utf-8"), encoding="utf-8"
    )
    return repo


def test_fix_dry_run_summarises_held_fixes_in_one_line(
    fixture_repo: Callable[[str], Path],
) -> None:
    repo = _planned_and_held_repo(fixture_repo)

    result = runner.invoke(app, ["fix", "--dry-run", "--path", str(repo)])

    assert result.exit_code == 0, result.output
    assert "docs/decisions/0004-no-backlink-adr.md: add implements" in result.output
    assert "planned 2 fix(es)" in result.output
    assert [line for line in result.output.splitlines() if "held" in line] == [_HELD_SUMMARY]


def test_fix_dry_run_with_confirm_lists_the_held_fixes_as_planned(
    fixture_repo: Callable[[str], Path],
) -> None:
    repo = _planned_and_held_repo(fixture_repo)

    result = runner.invoke(app, ["fix", "--dry-run", "--confirm", "--path", str(repo)])

    assert result.exit_code == 0, result.output
    assert f"{_HELD_RFC}: set status: stable" in result.output
    assert "planned 3 fix(es)" in result.output
    assert "held" not in result.output


def test_a_change_command_still_lists_each_held_fix(capsys: pytest.CaptureFixture[str]) -> None:
    from irminsul.cli import _echo_held

    held = Fix(Path(_HELD_RFC), "set status: stable", lambda text: text, requires_confirm=True)

    _echo_held(FixResult(held=[held]))

    assert capsys.readouterr().out == f"  held: {_HELD_RFC}: set status: stable\n"
