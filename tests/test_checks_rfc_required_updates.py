"""Tests for the required-update and planned-claim rules of RfcFollowThroughCheck."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

import pytest

from irminsul.checks.base import Finding
from irminsul.checks.rfc_follow_through import RfcFollowThroughCheck

from .conftest import by_doc, run_check, write, write_config


def _findings(repo: Path) -> list[Finding]:
    return run_check(RfcFollowThroughCheck, repo)


@pytest.fixture
def repo(fixture_repo: Callable[[str], Path]) -> Path:
    return fixture_repo("soft-lifecycle")


def test_good_accepted_rfc_is_silent(repo: Path) -> None:
    findings = _findings(repo)
    assert by_doc(findings, "0001-good") == []


def test_no_required_updates_field_warns(repo: Path) -> None:
    findings = by_doc(_findings(repo), "0002-no-required-updates-field")
    assert len(findings) == 1
    assert findings[0].code == "rfc-follow-through/no-required-updates-field"
    assert "no `required_updates` field" in findings[0].message


def test_missing_required_update_path_warns(repo: Path) -> None:
    findings = by_doc(_findings(repo), "0003-missing-path")
    assert len(findings) == 1
    assert findings[0].code == "rfc-follow-through/missing-required-update-path"
    assert "does not exist in the graph" in findings[0].message


def test_decision_doc_without_a_link_back_to_the_rfc_warns(repo: Path) -> None:
    findings = by_doc(_findings(repo), "0004-no-backlink-adr")
    assert len(findings) == 1
    assert "does not link back" in findings[0].message


def test_accepted_rfc_does_not_demand_an_implements_backlink(repo: Path) -> None:
    """`rfc-lifecycle` rejects the back-link until the RFC is implemented."""
    assert by_doc(_findings(repo), "accepted-target") == []


def test_resolved_by_adr_is_implicit_and_needs_no_required_update(repo: Path) -> None:
    findings = by_doc(_findings(repo), "0005-implicit-adr")
    assert findings == []


def test_depends_on_does_not_satisfy_required_update_backlink(repo: Path) -> None:
    findings = by_doc(_findings(repo), "depends-on-only")
    assert len(findings) == 1
    assert findings[0].code == "rfc-follow-through/update-missing-implements"


def test_broken_implements_is_a_lifecycle_error(repo: Path) -> None:
    from irminsul.checks.rfc_lifecycle import RfcLifecycleCheck

    findings = by_doc(run_check(RfcLifecycleCheck, repo), "broken-implements")
    assert [f.code for f in findings] == ["rfc-lifecycle/broken-implements"]
    assert "does not match any doc" in findings[0].message


def test_stale_planned_claim_warns(repo: Path) -> None:
    findings = by_doc(_findings(repo), "stale-claim")
    assert len(findings) == 1
    assert findings[0].code == "rfc-follow-through/stale-claim"
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
    assert "rfc-follow-through/no-required-updates-field" in {
        f.code for f in by_doc(findings, "0099-root-docs")
    }


_MISSING = "rfc-follow-through/missing-required-update-path"


def _rfc_repo(root: Path, state: str, kind: str) -> Path:
    write_config(root)
    write(
        root,
        "docs/rfcs/plan.md",
        f"---\nid: plan\ntitle: Plan\nstatus: stable\nrfc_state: {state}\n"
        "resolved_by: docs/decisions/choice.md\nrequired_updates:\n"
        f"  - path: docs/components/new-thing.md\n    kind: {kind}\n---\n\n# Plan\n\n"
        "## Resolution\n\nDone.\n",
    )
    write(
        root, "docs/decisions/choice.md", "---\nid: choice\ntitle: C\nstatus: stable\n---\n\n# C\n"
    )
    return root


def test_a_create_entry_is_not_missing_before_the_rfc_is_implemented(tmp_path: Path) -> None:
    root = _rfc_repo(tmp_path, "accepted", "create")

    assert _MISSING not in [f.code for f in _findings(root)]


def test_a_create_entry_must_exist_once_the_rfc_is_implemented(tmp_path: Path) -> None:
    root = _rfc_repo(tmp_path, "implemented", "create")

    assert [f.code for f in _findings(root) if f.code == _MISSING] == [_MISSING]


@pytest.mark.parametrize("kind", ["update", "review"])
def test_an_update_or_review_entry_must_exist_while_the_rfc_is_accepted(
    tmp_path: Path, kind: str
) -> None:
    root = _rfc_repo(tmp_path, "accepted", kind)

    assert [f.code for f in _findings(root) if f.code == _MISSING] == [_MISSING]
