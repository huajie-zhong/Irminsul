"""Tests for the required-update and planned-claim rules of RfcFollowThroughCheck."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

import pytest

from irminsul.checks.base import Finding
from irminsul.checks.rfc_follow_through import RfcFollowThroughCheck
from irminsul.config import find_config, load
from irminsul.docgraph import build_graph


def _findings(repo: Path) -> list[Finding]:
    config = load(find_config(repo))
    graph = build_graph(repo, config)
    return RfcFollowThroughCheck().run(graph)


def _by_doc(findings: list[Finding], doc_id: str) -> list[Finding]:
    return [f for f in findings if f.doc_id == doc_id]


@pytest.fixture
def repo(fixture_repo: Callable[[str], Path]) -> Path:
    return fixture_repo("soft-lifecycle")


def test_good_accepted_rfc_is_silent(repo: Path) -> None:
    findings = _findings(repo)
    assert _by_doc(findings, "0001-good") == []


def test_no_required_updates_field_warns(repo: Path) -> None:
    findings = _by_doc(_findings(repo), "0002-no-required-updates-field")
    assert len(findings) == 1
    assert findings[0].category == "no-required-updates-field"
    assert "no `required_updates` field" in findings[0].message


def test_missing_required_update_path_warns(repo: Path) -> None:
    findings = _by_doc(_findings(repo), "0003-missing-path")
    assert len(findings) == 1
    assert findings[0].category == "missing-required-update-path"
    assert "does not exist in the graph" in findings[0].message


def test_decision_doc_without_a_link_back_to_the_rfc_warns(repo: Path) -> None:
    findings = _by_doc(_findings(repo), "0004-no-backlink-adr")
    assert len(findings) == 1
    assert "does not link back" in findings[0].message


def test_accepted_rfc_does_not_demand_an_implements_backlink(repo: Path) -> None:
    """`rfc-lifecycle` rejects the back-link until the RFC is implemented."""
    assert _by_doc(_findings(repo), "accepted-target") == []


def test_resolved_by_adr_is_implicit_and_needs_no_required_update(repo: Path) -> None:
    findings = _by_doc(_findings(repo), "0005-implicit-adr")
    assert findings == []


def test_depends_on_does_not_satisfy_required_update_backlink(repo: Path) -> None:
    findings = _by_doc(_findings(repo), "depends-on-only")
    assert len(findings) == 1
    assert findings[0].category == "update-missing-implements"


def test_broken_implements_is_a_lifecycle_error(repo: Path) -> None:
    from irminsul.checks.rfc_lifecycle import RfcLifecycleCheck

    graph = build_graph(repo, load(find_config(repo)))
    findings = _by_doc(RfcLifecycleCheck().run(graph), "broken-implements")
    assert [f.category for f in findings] == ["broken-implements"]
    assert "does not match any doc" in findings[0].message


def test_stale_planned_claim_warns(repo: Path) -> None:
    findings = _by_doc(_findings(repo), "stale-claim")
    assert len(findings) == 1
    assert findings[0].category == "stale-claim"
    assert "is now implemented" in findings[0].message


def test_rfc_prefix_honours_repo_root_docs_root() -> None:
    """Projects can set `paths.docs_root = "."`; RFC detection still applies."""
    from irminsul.config import IrminsulConfig, Paths
    from irminsul.docgraph import DocGraph, DocNode
    from irminsul.frontmatter import DocFrontmatter, RfcStateEnum, StatusEnum

    fm = DocFrontmatter(
        id="0099-root-docs",
        title="Root docs RFC",
        status=StatusEnum.stable,
        rfc_state=RfcStateEnum.accepted,
        resolved_by="decisions/0099-root-docs.md",
    )
    path = Path("rfcs/0099-root-docs.md")
    node = DocNode(id="0099-root-docs", path=path, frontmatter=fm, body="# x")
    config = IrminsulConfig(paths=Paths(docs_root="."))
    graph = DocGraph(nodes={"0099-root-docs": node}, by_path={path: node}, config=config)

    findings = RfcFollowThroughCheck().run(graph)
    assert "no-required-updates-field" in {f.category for f in _by_doc(findings, "0099-root-docs")}
