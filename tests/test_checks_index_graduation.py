"""Tests for IndexGraduationCheck."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from irminsul.checks.base import Severity
from irminsul.checks.index_graduation import IndexGraduationCheck
from irminsul.config import find_config, load
from irminsul.docgraph import build_graph


def _findings(repo: Path) -> list:
    config = load(find_config(repo))
    graph = build_graph(repo, config)
    return IndexGraduationCheck().run(graph)


def test_good_fixture_has_no_findings(fixture_repo: Callable[[str], Path]) -> None:
    assert _findings(fixture_repo("good")) == []


def test_populated_draft_index_is_flagged(fixture_repo: Callable[[str], Path]) -> None:
    """Only the filled+draft layer warns; filled+stable and hollow+draft don't."""
    findings = _findings(fixture_repo("soft-index-graduation"))
    assert len(findings) == 1
    f = findings[0]
    assert "20-components" in f.message
    assert "graduate" in f.message
    assert f.path.as_posix().endswith("20-components/INDEX.md")


def test_hollow_draft_is_not_graduation_business(fixture_repo: Callable[[str], Path]) -> None:
    findings = _findings(fixture_repo("soft-index-graduation"))
    assert all("60-operations" not in f.message for f in findings)


def test_fix_sets_status_stable(fixture_repo: Callable[[str], Path]) -> None:
    repo = fixture_repo("soft-index-graduation")
    config = load(find_config(repo))
    graph = build_graph(repo, config)
    check = IndexGraduationCheck()
    findings = check.run(graph)
    fixes = check.fixes(findings, graph)
    assert len(fixes) == 1
    index = repo / "docs/20-components/INDEX.md"
    fixed = fixes[0].apply(index.read_text(encoding="utf-8"))
    assert "status: stable" in fixed
    assert "status: draft" not in fixed
    # Re-running the check on the fixed text yields no finding.
    index.write_text(fixed, encoding="utf-8")
    assert IndexGraduationCheck().run(build_graph(repo, config)) == []


def test_check_registered_in_soft_registry() -> None:
    from irminsul.checks import SOFT_REGISTRY

    assert SOFT_REGISTRY[IndexGraduationCheck.name] is IndexGraduationCheck
    assert IndexGraduationCheck.default_severity == Severity.warning
