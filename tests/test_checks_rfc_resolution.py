"""Tests for RfcResolutionCheck (RFC-0017)."""

from __future__ import annotations

import datetime as _dt
from collections.abc import Callable
from pathlib import Path

import pytest

from irminsul.checks.base import Finding, Severity
from irminsul.checks.rfc_resolution import RfcResolutionCheck
from irminsul.config import find_config, load
from irminsul.docgraph import build_graph


def _findings(repo: Path, *, now: _dt.date | None = None) -> list[Finding]:
    config = load(find_config(repo))
    graph = build_graph(repo, config, now=now)
    return RfcResolutionCheck().run(graph)


def _by_doc(findings: list[Finding], doc_id: str) -> list[Finding]:
    return [f for f in findings if f.doc_id == doc_id]


@pytest.fixture
def repo(fixture_repo: Callable[[str], Path]) -> Path:
    return fixture_repo("soft-rfc-resolution")


def test_good_accepted_rfc_is_silent(repo: Path) -> None:
    findings = _findings(repo, now=_dt.date(2025, 1, 1))
    assert _by_doc(findings, "0001-accepted-good") == []
    assert _by_doc(findings, "0001-good-adr") == []


def test_accepted_but_status_draft_warns(repo: Path) -> None:
    findings = _findings(repo, now=_dt.date(2025, 1, 1))
    matched = _by_doc(findings, "0002-accepted-bad-status")
    assert any("status is 'draft'" in f.message for f in matched)
    assert all(f.severity == Severity.warning for f in matched)


def test_accepted_resolved_by_unknown_warns(repo: Path) -> None:
    findings = _findings(repo, now=_dt.date(2025, 1, 1))
    matched = _by_doc(findings, "0003-accepted-broken-link")
    assert any("no such doc was found" in f.message for f in matched)


def test_accepted_missing_backlink_warns(repo: Path) -> None:
    findings = _findings(repo, now=_dt.date(2025, 1, 1))
    matched = _by_doc(findings, "0004-no-backlink-adr")
    assert any("does not link back" in f.message for f in matched)


def test_withdrawn_with_loose_ends_warns(repo: Path) -> None:
    findings = _findings(repo, now=_dt.date(2025, 1, 1))
    matched = _by_doc(findings, "0005-withdrawn-bad")
    msgs = [f.message for f in matched]
    assert any("status is 'draft'" in m for m in msgs)
    assert any("Withdrawal Rationale" in m for m in msgs)
    assert any("Unresolved Questions" in m for m in msgs)


def test_rejected_with_rationale_is_silent(repo: Path) -> None:
    findings = _findings(repo, now=_dt.date(2025, 1, 1))
    assert _by_doc(findings, "0006-rejected-good") == []


def test_target_decision_date_past_warns(repo: Path) -> None:
    findings = _findings(repo, now=_dt.date(2025, 1, 1))
    matched = _by_doc(findings, "0007-stale-target")
    assert any("target_decision_date" in f.message for f in matched)


def test_target_decision_date_future_is_silent(repo: Path) -> None:
    findings = _findings(repo, now=_dt.date(2020, 1, 1))
    matched = _by_doc(findings, "0007-stale-target")
    assert all("target_decision_date" not in f.message for f in matched)


def test_check_ignores_non_rfc_docs(repo: Path) -> None:
    findings = _findings(repo, now=_dt.date(2025, 1, 1))
    # The 0001-good-adr doc lives outside docs/80-evolution/rfcs/ and has no
    # rfc_state, so the check must not fire on it.
    assert _by_doc(findings, "0001-good-adr") == []


def test_withdrawn_state_emits_deprecation_warning(repo: Path) -> None:
    findings = _findings(repo, now=_dt.date(2025, 1, 1))
    matched = [
        f for f in _by_doc(findings, "0005-withdrawn-bad") if f.category == "deprecated-rfc-state"
    ]
    assert len(matched) == 1
    assert "'withdrawn'" in matched[0].message
    assert "rejected" in matched[0].message


def test_deprecated_state_fix_rewrites_rfc_state(repo: Path) -> None:
    from irminsul.config import find_config, load
    from irminsul.docgraph import build_graph

    config = load(find_config(repo))
    graph = build_graph(repo, config, now=_dt.date(2025, 1, 1))
    check = RfcResolutionCheck()
    findings = check.run(graph)
    fixes = check.fixes(findings, graph)
    matched = [f for f in fixes if "rfc_state: rejected" in f.description]
    assert len(matched) == 1
    assert matched[0].requires_confirm

    node = graph.nodes["0005-withdrawn-bad"]
    original = (repo / node.path).read_text(encoding="utf-8")
    rewritten = matched[0].apply(original)
    assert "rfc_state: rejected" in rewritten
    assert "rfc_state: withdrawn" not in rewritten


def test_implemented_rfc_checked_like_accepted() -> None:
    from irminsul.config import IrminsulConfig
    from irminsul.docgraph import DocGraph, DocNode
    from irminsul.frontmatter import AudienceEnum, DocFrontmatter, RfcStateEnum, StatusEnum

    fm = DocFrontmatter(
        id="0100-implemented",
        title="Implemented without resolution section",
        audience=AudienceEnum.explanation,
        tier=2,
        status=StatusEnum.draft,
        rfc_state=RfcStateEnum.implemented,
        resolved_by="docs/50-decisions/0001-adr.md",
    )
    path = Path("docs/80-evolution/rfcs/0100-implemented.md")
    node = DocNode(id="0100-implemented", path=path, frontmatter=fm, body="# x")
    graph = DocGraph(
        nodes={"0100-implemented": node},
        by_path={path: node},
        config=IrminsulConfig(),
        now=_dt.date(2026, 1, 1),
    )

    findings = RfcResolutionCheck().run(graph)
    messages = [f.message for f in findings]
    assert any("rfc_state: implemented but status is 'draft'" in m for m in messages)
    assert any("implemented RFC is missing a '## Resolution' section" in m for m in messages)
    assert any("no such doc was found" in m for m in messages)
    assert all(f.category != "deprecated-rfc-state" for f in findings)


def test_rfc_prefix_honours_custom_docs_root() -> None:
    """Projects can override `paths.docs_root`; the check must follow."""
    from irminsul.config import IrminsulConfig, Paths
    from irminsul.docgraph import DocGraph, DocNode
    from irminsul.frontmatter import AudienceEnum, DocFrontmatter, RfcStateEnum, StatusEnum

    fm = DocFrontmatter(
        id="0099-stale",
        title="Stale draft",
        audience=AudienceEnum.explanation,
        tier=2,
        status=StatusEnum.draft,
        rfc_state=RfcStateEnum.draft,
        target_decision_date="2024-01-01",
    )
    path = Path("documentation/80-evolution/rfcs/0099-stale.md")
    node = DocNode(id="0099-stale", path=path, frontmatter=fm, body="# x")
    config = IrminsulConfig(paths=Paths(docs_root="documentation"))
    graph = DocGraph(
        nodes={"0099-stale": node},
        by_path={path: node},
        config=config,
        now=_dt.date(2026, 1, 1),
    )

    findings = RfcResolutionCheck().run(graph)
    assert any("target_decision_date" in f.message for f in findings)
