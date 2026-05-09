"""Tests for PhantomLayerCheck."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from irminsul.checks.phantom_layer import PhantomLayerCheck
from irminsul.config import find_config, load
from irminsul.docgraph import build_graph


def _findings(repo: Path) -> list:
    config = load(find_config(repo))
    graph = build_graph(repo, config)
    return PhantomLayerCheck().run(graph)


def test_good_fixture_has_no_phantom_findings(fixture_repo: Callable[[str], Path]) -> None:
    repo = fixture_repo("good")
    findings = _findings(repo)
    assert findings == []


def test_hollow_directory_flagged(fixture_repo: Callable[[str], Path]) -> None:
    repo = fixture_repo("bad-phantom")
    findings = _findings(repo)
    assert len(findings) == 1
    assert "phantom layer" in findings[0].message
    assert "30-workflows" in findings[0].message


def test_finding_has_path(fixture_repo: Callable[[str], Path]) -> None:
    repo = fixture_repo("bad-phantom")
    findings = _findings(repo)
    assert len(findings) == 1
    assert findings[0].path is not None
    assert str(findings[0].path).endswith("INDEX.md")
