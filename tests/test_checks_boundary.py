"""Tests for BoundaryCheck."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from irminsul.checks import Severity
from irminsul.checks.boundary import BoundaryCheck
from irminsul.config import load
from irminsul.docgraph import build_graph


def _run(repo: Path) -> list:
    cfg = load(repo / "irminsul.toml")
    graph = build_graph(repo, cfg)
    return BoundaryCheck().run(graph)


def test_good_fixture_has_no_boundary_findings(
    fixture_repo: Callable[[str], Path],
) -> None:
    findings = _run(fixture_repo("good"))
    assert findings == []


def test_missing_scope_section_flagged(
    fixture_repo: Callable[[str], Path],
) -> None:
    findings = _run(fixture_repo("soft-boundary"))
    assert len(findings) == 1
    assert findings[0].severity == Severity.warning
    assert "Scope & Limitations" in findings[0].message


def test_finding_has_path(
    fixture_repo: Callable[[str], Path],
) -> None:
    findings = _run(fixture_repo("soft-boundary"))
    assert findings[0].path is not None
    assert "widget.md" in findings[0].path.as_posix()
