"""Tests for DuplicateBlockCheck."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

import pytest

from irminsul.checks.base import Finding
from irminsul.checks.duplicate_block import DuplicateBlockCheck

from .conftest import run_check, write_config


@pytest.fixture
def repo(fixture_repo: Callable[[str], Path]) -> Path:
    return fixture_repo("soft-doc-structure")


def _lines_flagged(repo: Path, findings: list[Finding], rel: str) -> list[str]:
    text = (repo / rel).read_text(encoding="utf-8").splitlines()
    return [text[f.line - 1] for f in findings if f.path and f.path.as_posix() == rel and f.line]


def test_repeated_list_item_is_reported_at_second_occurrence(repo: Path) -> None:
    findings = run_check(DuplicateBlockCheck, repo)

    assert len(findings) == 1
    assert findings[0].code == "duplicate-block/repeated-block"
    assert findings[0].line == 12
    assert "line 10" in findings[0].message


def test_short_repeats_and_fenced_copies_are_ignored(repo: Path) -> None:
    findings = run_check(DuplicateBlockCheck, repo)
    assert not [f for f in findings if f.line != 12]


def test_a_block_copied_into_another_live_doc_is_reported_once(tmp_path: Path) -> None:
    write_config(tmp_path)
    shared = "Source discovery walks every configured root and skips paths the ignore list names.\n"
    for rel, status in (
        ("guides/a.md", "stable"),
        ("guides/b.md", "stable"),
        ("guides/c.md", "draft"),
    ):
        doc = tmp_path / "docs" / rel
        doc.parent.mkdir(parents=True, exist_ok=True)
        doc.write_text(
            f"---\nid: {doc.stem}\ntitle: T\nstatus: {status}\n---\n\n# T\n\n{shared}",
            encoding="utf-8",
        )
    findings = run_check(DuplicateBlockCheck, tmp_path)
    assert [(f.code, f.path.as_posix()) for f in findings] == [
        ("duplicate-block/copied-block", "docs/guides/b.md")
    ]
    assert findings[0].data["first"] == "docs/guides/a.md:9"


def test_a_paragraph_repeated_under_another_heading_is_reported(tmp_path: Path) -> None:
    """A heading ends a block; it does not scope the comparison. Two sections restating
    one paragraph are exactly the pair that drifts apart, so narrowing this check to
    within-a-section would drop the case it is most useful for."""
    write_config(tmp_path)
    shared = "Source discovery walks every configured root and skips paths the ignore list names."
    doc = tmp_path / "docs" / "guides" / "a.md"
    doc.parent.mkdir(parents=True, exist_ok=True)
    doc.write_text(
        f"---\nid: a\ntitle: T\nstatus: stable\n---\n\n# T\n\n## Walking\n\n{shared}\n\n"
        f"## Ignoring\n\n{shared}\n",
        encoding="utf-8",
    )

    findings = run_check(DuplicateBlockCheck, tmp_path)

    assert [f.code for f in findings] == ["duplicate-block/repeated-block"]
    assert findings[0].line == 15
