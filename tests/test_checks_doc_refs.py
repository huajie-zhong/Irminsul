"""Tests for DocRefsCheck."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from irminsul.checks.base import Finding, Severity
from irminsul.checks.doc_refs import DocRefsCheck
from irminsul.config import find_config, load
from irminsul.docgraph import build_graph


def _findings(repo: Path) -> list[Finding]:
    config = load(find_config(repo))
    graph = build_graph(repo, config)
    return DocRefsCheck().run(graph)


def test_dangling_depends_on_warned(fixture_repo: Callable[[str], Path]) -> None:
    repo = fixture_repo("soft-doc-refs")
    findings = _findings(repo)
    assert len(findings) == 1
    finding = findings[0]
    assert finding.severity == Severity.warning
    assert "ghost-doc" in finding.message
    assert finding.path is not None
    assert finding.path.as_posix() == "docs/20-components/beta.md"
    assert finding.doc_id == "beta"


def test_dangling_entry_line_points_at_frontmatter(
    fixture_repo: Callable[[str], Path],
) -> None:
    repo = fixture_repo("soft-doc-refs")
    findings = _findings(repo)
    assert len(findings) == 1
    # `- ghost-doc` is line 8 of beta.md's frontmatter block.
    assert findings[0].line == 8


def test_suggestion_names_refs_query(fixture_repo: Callable[[str], Path]) -> None:
    repo = fixture_repo("soft-doc-refs")
    findings = _findings(repo)
    assert len(findings) == 1
    assert findings[0].suggestion is not None
    assert "irminsul refs ghost-doc" in findings[0].suggestion


def test_valid_depends_on_silent(fixture_repo: Callable[[str], Path]) -> None:
    repo = fixture_repo("soft-doc-refs")
    findings = _findings(repo)
    # alpha -> beta resolves; only beta's dangling entry is flagged.
    assert all(f.doc_id != "alpha" for f in findings)


def test_fixed_id_goes_green(fixture_repo: Callable[[str], Path]) -> None:
    repo = fixture_repo("soft-doc-refs")
    beta = repo / "docs" / "20-components" / "beta.md"
    beta.write_text(
        beta.read_text(encoding="utf-8").replace("ghost-doc", "alpha"),
        encoding="utf-8",
    )
    assert _findings(repo) == []
