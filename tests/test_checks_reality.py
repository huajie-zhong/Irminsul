"""Tests for RealityCheck."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from irminsul.checks.reality import RealityCheck
from irminsul.config import load
from irminsul.docgraph import build_graph


def _run(repo: Path) -> list:
    cfg = load(repo / "irminsul.toml")
    graph = build_graph(repo, cfg)
    return RealityCheck().run(graph)


def test_good_fixture_has_no_reality_findings(
    fixture_repo: Callable[[str], Path],
) -> None:
    findings = _run(fixture_repo("good"))
    assert findings == []


def test_speculative_keywords_flagged(
    fixture_repo: Callable[[str], Path],
) -> None:
    findings = _run(fixture_repo("soft-reality"))
    assert len(findings) >= 1
    messages = [f.message for f in findings]
    assert any(
        "planned" in m or "sprint" in m or "deferred" in m or "roadmap" in m for m in messages
    )


def test_findings_have_line_numbers(
    fixture_repo: Callable[[str], Path],
) -> None:
    findings = _run(fixture_repo("soft-reality"))
    assert all(f.line is not None and f.line > 0 for f in findings)


def test_only_tier3_docs_checked(
    fixture_repo: Callable[[str], Path],
) -> None:
    findings = _run(fixture_repo("soft-reality"))
    assert all(f.path is not None and "20-components" in f.path.as_posix() for f in findings)
