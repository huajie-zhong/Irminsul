"""Tests for RfcFollowThroughCheck."""

from __future__ import annotations

import datetime as _dt
from collections.abc import Callable
from pathlib import Path

import pytest

from irminsul.checks.base import Finding, Severity
from irminsul.checks.rfc_follow_through import RfcFollowThroughCheck

from .conftest import by_doc, commit_all, git_init, load_graph, run_check, write, write_config


def _findings(repo: Path, *, now: _dt.date | None = None, **graph_kwargs: object) -> list[Finding]:
    return run_check(RfcFollowThroughCheck, repo, now=now, **graph_kwargs)


@pytest.fixture
def repo(fixture_repo: Callable[[str], Path]) -> Path:
    return fixture_repo("soft-rfc-follow-through")


def test_good_accepted_rfc_is_silent(repo: Path) -> None:
    findings = _findings(repo, now=_dt.date(2025, 1, 1))
    assert by_doc(findings, "0001-accepted-good") == []
    assert by_doc(findings, "0001-good-adr") == []


def test_accepted_but_status_draft_is_an_error(repo: Path) -> None:
    findings = _findings(repo, now=_dt.date(2025, 1, 1))
    matched = by_doc(findings, "0002-accepted-bad-status")
    assert any("status is 'draft'" in f.message for f in matched)
    assert all(f.severity == Severity.error for f in matched)


def test_accepted_resolved_by_unknown_is_a_lifecycle_error(repo: Path) -> None:
    from irminsul.checks.rfc_lifecycle import RfcLifecycleCheck

    matched = by_doc(run_check(RfcLifecycleCheck, repo), "0003-accepted-broken-link")
    assert [f.code for f in matched] == ["rfc-lifecycle/dangling-resolved-by"]
    assert matched[0].severity == Severity.error


def test_decision_doc_without_a_link_back_warns(repo: Path) -> None:
    findings = _findings(repo, now=_dt.date(2025, 1, 1))
    matched = by_doc(findings, "0004-no-backlink-adr")
    assert any("does not link back" in f.message for f in matched)


def test_rejected_with_rationale_is_silent(repo: Path) -> None:
    findings = _findings(repo, now=_dt.date(2025, 1, 1))
    assert by_doc(findings, "0006-rejected-good") == []


def test_target_decision_date_past_warns(repo: Path) -> None:
    findings = _findings(repo, now=_dt.date(2025, 1, 1))
    matched = by_doc(findings, "0007-stale-target")
    assert any("target_decision_date" in f.message for f in matched)


def test_target_decision_date_future_is_silent(repo: Path) -> None:
    findings = _findings(repo, now=_dt.date(2020, 1, 1))
    matched = by_doc(findings, "0007-stale-target")
    assert all("target_decision_date" not in f.message for f in matched)


def test_check_ignores_non_rfc_docs(repo: Path) -> None:
    findings = _findings(repo, now=_dt.date(2025, 1, 1))
    # The 0001-good-adr doc lives outside docs/rfcs/ and has no
    # rfc_state, so the check must not fire on it.
    assert by_doc(findings, "0001-good-adr") == []


def test_implemented_rfc_checked_like_accepted() -> None:
    from irminsul.config import IrminsulConfig
    from irminsul.docgraph import DocGraph, DocNode
    from irminsul.frontmatter import DocFrontmatter, RfcStateEnum, StatusEnum

    fm = DocFrontmatter(
        id="0100-implemented",
        title="Implemented without resolution section",
        status=StatusEnum.draft,
        rfc_state=RfcStateEnum.implemented,
        resolved_by="docs/decisions/0001-adr.md",
    )
    path = Path("docs/rfcs/0100-implemented.md")
    node = DocNode(id="0100-implemented", path=path, frontmatter=fm, body="# x")
    graph = DocGraph(
        nodes={"0100-implemented": node},
        by_path={path: node},
        config=IrminsulConfig(),
        now=_dt.date(2026, 1, 1),
    )

    findings = RfcFollowThroughCheck().run(graph)
    messages = [f.message for f in findings]
    assert any("rfc_state: implemented but status is 'draft'" in m for m in messages)
    assert any("implemented RFC is missing a '## Resolution' section" in m for m in messages)


def test_rfc_prefix_honours_custom_docs_root() -> None:
    """Projects can override `paths.docs_root`; the check must follow."""
    from irminsul.config import IrminsulConfig, Paths
    from irminsul.docgraph import DocGraph, DocNode
    from irminsul.frontmatter import DocFrontmatter, RfcStateEnum, StatusEnum

    fm = DocFrontmatter(
        id="0099-stale",
        title="Stale draft",
        status=StatusEnum.draft,
        rfc_state=RfcStateEnum.draft,
        target_decision_date="2024-01-01",
    )
    path = Path("documentation/rfcs/0099-stale.md")
    node = DocNode(id="0099-stale", path=path, frontmatter=fm, body="# x")
    config = IrminsulConfig(paths=Paths(docs_root="documentation"))
    graph = DocGraph(
        nodes={"0099-stale": node},
        by_path={path: node},
        config=config,
        now=_dt.date(2026, 1, 1),
    )

    findings = RfcFollowThroughCheck().run(graph)
    assert any("target_decision_date" in f.message for f in findings)


def _accepted_repo(root: Path, *, followed: bool) -> Path:
    git_init(root)
    write_config(root)
    write(
        root,
        "docs/rfcs/plan.md",
        "---\nid: plan\ntitle: Plan\nstatus: stable\nrfc_state: accepted\n"
        "resolved_by: docs/decisions/choice.md\nrequired_updates:\n"
        "  - path: docs/components/core.md\n    kind: update\n---\n\n# Plan\n\n"
        "## Resolution\n\nAccepted.\n",
    )
    write(
        root, "docs/decisions/choice.md", "---\nid: choice\ntitle: C\nstatus: stable\n---\n\n# C\n"
    )
    core = "---\nid: core\ntitle: Core\nstatus: stable\n---\n\n# Core\n"
    rfc = (root / "docs/rfcs/plan.md").read_text(encoding="utf-8")
    (root / "docs/rfcs/plan.md").unlink()
    write(root, "docs/components/core.md", core)
    commit_all(root, "x", when="2025-12-01T12:00:00")
    write(root, "docs/rfcs/plan.md", rfc)
    commit_all(root, "x", when="2026-01-01T12:00:00")
    if followed:
        write(root, "docs/components/core.md", core + "\nDone.\n")
        commit_all(root, "x", when="2026-02-01T12:00:00")
    return root


def test_an_accepted_rfc_nothing_follows_goes_stale(tmp_path: Path) -> None:
    root = _accepted_repo(tmp_path, followed=False)
    codes = [f.code for f in _findings(root, now=_dt.date(2026, 3, 1))]
    assert "rfc-follow-through/accepted-not-implemented" not in codes
    later = _findings(root, now=_dt.date(2026, 4, 2))
    stale = [f for f in later if f.code == "rfc-follow-through/accepted-not-implemented"]
    assert [(f.doc_id, f.severity.value) for f in stale] == [("plan", "warning")]


def test_an_accepted_rfc_whose_named_doc_changed_does_not_go_stale(tmp_path: Path) -> None:
    root = _accepted_repo(tmp_path, followed=True)
    later = _findings(root, now=_dt.date(2026, 6, 1))
    assert "rfc-follow-through/accepted-not-implemented" not in [f.code for f in later]


def test_an_uncommitted_edit_to_a_named_doc_counts_as_following_through(tmp_path: Path) -> None:
    root = _accepted_repo(tmp_path, followed=False)
    later = _dt.date(2026, 4, 2)
    stale = "rfc-follow-through/accepted-not-implemented"
    assert stale in [f.code for f in _findings(root, now=later)]

    core = root / "docs/components/core.md"
    core.write_text(core.read_text(encoding="utf-8") + "\nDone.\n", encoding="utf-8")

    assert stale not in [f.code for f in _findings(root, now=later)]
    assert stale in [f.code for f in _findings(root, now=later, committed_only=True)]


def test_a_planned_claim_citing_a_resolved_rfc_is_reported_once(tmp_path: Path) -> None:
    """`claim-provenance` reported the same claim as `planned-claim-resolved`, beside this
    check's `stale-claim`."""
    from irminsul.checks.claim_provenance import ClaimProvenanceCheck

    repo = tmp_path / "r"
    (repo / "docs" / "rfcs").mkdir(parents=True)
    (repo / "docs" / "foundation").mkdir(parents=True)
    write_config(repo)
    (repo / "docs" / "rfcs" / "0001-done.md").write_text(
        "---\nid: 0001-done\ntitle: Done\nstatus: stable\nrfc_state: implemented\n"
        "resolved_by: docs/foundation/principles.md\n---\n\n# Done\n",
        encoding="utf-8",
    )
    (repo / "docs" / "foundation" / "principles.md").write_text(
        "---\nid: principles\ntitle: Principles\nstatus: stable\nclaims:\n"
        "  - id: shipped\n    state: planned\n    kind: feature\n"
        "    claim: The feature ships.\n    evidence:\n      - docs/rfcs/0001-done.md\n"
        "---\n\n# Principles\n\nThe feature ships. <!-- claim:shipped -->\n",
        encoding="utf-8",
    )
    graph = load_graph(repo)

    findings = ClaimProvenanceCheck().run(graph) + RfcFollowThroughCheck().run(graph)

    assert [f.code for f in findings if "shipped" in f.message] == [
        "rfc-follow-through/stale-claim"
    ]
