"""Tests for the GlobsCheck."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

import pytest

import irminsul.source_tree as source_tree_module
from irminsul.checks import Severity
from irminsul.checks.globs import GlobsCheck, SourceWalkIssue, SourceWalkResult

from .conftest import run_check


def _run(repo: Path) -> list:
    return run_check(GlobsCheck, repo)


def test_good_fixture_has_no_glob_findings(
    fixture_repo: Callable[[str], Path],
) -> None:
    findings = _run(fixture_repo("good"))
    assert [f for f in findings if f.severity == Severity.error] == []


def test_bad_globs_fixture_flags_each_unmatched_pattern(
    fixture_repo: Callable[[str], Path],
) -> None:
    findings = _run(fixture_repo("bad-globs"))
    error_messages = [f.message for f in findings if f.severity == Severity.error]

    # The real pattern (app/real.py) should NOT be flagged.
    assert not any("app/real.py" in m for m in error_messages)
    # The two dead patterns should both be flagged.
    assert any("app/missing/*.py" in m for m in error_messages)
    assert any("lib/ghost.py" in m for m in error_messages)


def test_missing_source_root_warns(tmp_path: Path) -> None:
    (tmp_path / "irminsul.toml").write_text(
        'project_name = "missing-root"\n\n'
        '[paths]\ndocs_root = "docs"\nsource_roots = ["does-not-exist"]\n',
        encoding="utf-8",
    )
    (tmp_path / "docs" / "components").mkdir(parents=True)
    (tmp_path / "docs" / "components" / "x.md").write_text(
        "---\nid: x\ntitle: X\nstatus: stable\n---\nbody\n",
        encoding="utf-8",
    )
    findings = run_check(GlobsCheck, tmp_path)

    assert any(f.severity == Severity.warning and "does-not-exist" in f.message for f in findings)


def test_source_walk_issues_become_glob_findings(
    fixture_repo: Callable[[str], Path],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repo = fixture_repo("good")
    result = SourceWalkResult(
        files=[(repo / "app" / "composer.py", "app/composer.py")],
        missing_roots=[],
        issues=[
            SourceWalkIssue(
                kind="source-root-escape",
                root="app",
                path="app/escape.py",
                message="escape",
            ),
            SourceWalkIssue(
                kind="broken-symlink",
                root="app",
                path="app/broken.py",
                message="broken",
            ),
        ],
    )
    monkeypatch.setattr(source_tree_module, "walk_configured_source_files", lambda *_: result)

    findings = _run(repo)

    by_code = {finding.code: finding for finding in findings}
    assert by_code["globs/source-root-escape"].severity == Severity.error
    assert by_code["globs/broken-symlink"].severity == Severity.warning
