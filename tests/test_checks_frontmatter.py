"""Tests for the FrontmatterCheck."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from irminsul.checks import Severity
from irminsul.checks.frontmatter import FrontmatterCheck
from irminsul.config import load
from irminsul.docgraph import build_graph


def _run(repo: Path) -> list:
    cfg = load(repo / "irminsul.toml")
    graph = build_graph(repo, cfg)
    return FrontmatterCheck().run(graph)


def test_good_fixture_has_no_frontmatter_findings(
    fixture_repo: Callable[[str], Path],
) -> None:
    findings = _run(fixture_repo("good"))
    assert findings == []


def test_bad_frontmatter_fixture_reports_each_failure_mode(
    fixture_repo: Callable[[str], Path],
) -> None:
    findings = _run(fixture_repo("bad-frontmatter"))
    messages = [f.message for f in findings]

    # Every finding from this check is severity=error.
    assert all(f.severity == Severity.error for f in findings)
    # Parse error for bad-tier (validation failure).
    assert any("parse error" in m and "tier" in m for m in messages)
    # Parse error for missing-audience.
    assert any("parse error" in m and "audience" in m for m in messages)
    # Missing-frontmatter file.
    assert any("missing frontmatter" in m for m in messages)
    # ID/filename mismatch.
    assert any("does not match filename" in m for m in messages)
