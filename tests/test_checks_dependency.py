"""Tests for DependencyCheck (import-deps)."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from irminsul.checks.dependency_check import DependencyCheck
from irminsul.config import find_config, load
from irminsul.docgraph import build_graph


def _findings(repo: Path) -> list:
    config = load(find_config(repo))
    graph = build_graph(repo, config)
    return DependencyCheck().run(graph)


def test_hallucinated_dep_flagged(fixture_repo: Callable[[str], Path]) -> None:
    repo = fixture_repo("bad-dependency")
    findings = _findings(repo)
    hallucinated = [f for f in findings if "declared but no import" in f.message]
    assert any("renderer" in f.message for f in hallucinated)


def test_good_fixture_no_findings(fixture_repo: Callable[[str], Path]) -> None:
    repo = fixture_repo("good")
    assert _findings(repo) == []
