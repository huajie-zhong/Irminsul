"""Tests for ParentChildCheck."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from irminsul.checks.base import Severity
from irminsul.checks.parent_child import ParentChildCheck

from .conftest import run_check, write_config


def _findings(repo: Path) -> list:
    return run_check(ParentChildCheck, repo)


def test_broad_glob_with_children_warns(fixture_repo: Callable[[str], Path]) -> None:
    repo = fixture_repo("soft-parent-child")
    findings = _findings(repo)
    warnings = [f for f in findings if f.severity == Severity.warning]
    assert any("wildcard" in f.message for f in warnings)


def test_index_auto_owns_siblings_no_warnings(tmp_path: Path) -> None:
    """INDEX auto-owns all siblings; no warnings are emitted for sibling presence."""
    repo = tmp_path / "r"
    repo.mkdir()
    write_config(repo, source_roots=["app"], enabled=["parent-child"])
    (repo / "app").mkdir()
    docs = repo / "docs" / "components" / "thing"
    docs.mkdir(parents=True)
    (docs / "INDEX.md").write_text(
        "---\nid: thing\ntitle: Thing\n"
        "status: stable\n"
        "describes: []\n---\n\n# Thing\n\n- [`sibling`](sibling.md) — a sibling\n",
        encoding="utf-8",
    )
    (docs / "sibling.md").write_text(
        "---\nid: sibling\ntitle: Sibling\nstatus: stable\n---\n\n# Sibling\n",
        encoding="utf-8",
    )

    findings = run_check(ParentChildCheck, repo)
    warnings = [f for f in findings if f.severity == Severity.warning]
    assert not any("sibling" in f.message for f in warnings)


def test_an_index_need_not_link_its_siblings(tmp_path: Path) -> None:
    """The folder is the list: the agent manifest names every doc with its summary, so an
    INDEX that links none of its siblings is complete."""
    repo = tmp_path / "r"
    docs = repo / "docs" / "guides"
    docs.mkdir(parents=True)
    write_config(repo)
    (docs / "INDEX.md").write_text(
        "---\nid: guides\ntitle: Guides\nstatus: stable\n---\n\n# Guides\n\nHow-tos.\n",
        encoding="utf-8",
    )
    (docs / "unlinked.md").write_text(
        "---\nid: unlinked\ntitle: Unlinked\nstatus: stable\n---\n\n# x\n", encoding="utf-8"
    )

    assert _findings(repo) == []
