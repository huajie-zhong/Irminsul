"""Tests for same-doc + cross-doc anchor validation in LinksCheck."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from irminsul.checks.links import LinksCheck
from irminsul.config import find_config, load
from irminsul.docgraph import build_graph


def _findings(repo: Path) -> list:
    config = load(find_config(repo))
    graph = build_graph(repo, config)
    return LinksCheck().run(graph)


def test_unknown_same_doc_anchor_errors(fixture_repo: Callable[[str], Path]) -> None:
    repo = fixture_repo("bad-anchors")
    findings = _findings(repo)
    msgs = [f.message for f in findings]
    assert any("nonexistent-section" in m for m in msgs)


def test_known_same_doc_anchor_ok(fixture_repo: Callable[[str], Path]) -> None:
    repo = fixture_repo("bad-anchors")
    findings = _findings(repo)
    msgs = [f.message for f in findings]
    assert not any("section-one" in m for m in msgs)


def test_unknown_cross_doc_anchor_errors(fixture_repo: Callable[[str], Path]) -> None:
    repo = fixture_repo("bad-anchors")
    findings = _findings(repo)
    msgs = [f.message for f in findings]
    assert any("nonexistent" in m and "two.md" in m for m in msgs)


def test_known_cross_doc_anchor_ok(fixture_repo: Callable[[str], Path]) -> None:
    repo = fixture_repo("bad-anchors")
    findings = _findings(repo)
    msgs = [f.message for f in findings]
    # The "section-two" cross-doc link should not be flagged.
    flagged_section_two = [m for m in msgs if "section-two" in m and "no matching heading" in m]
    assert not flagged_section_two
