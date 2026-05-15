"""Tests for DecisionFollowupsCheck (RFC-0018)."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

import pytest

from irminsul.checks.base import Finding
from irminsul.checks.decision_followups import DecisionFollowupsCheck
from irminsul.config import find_config, load
from irminsul.docgraph import build_graph


def _findings(repo: Path) -> list[Finding]:
    config = load(find_config(repo))
    graph = build_graph(repo, config)
    return DecisionFollowupsCheck().run(graph)


def _by_doc(findings: list[Finding], doc_id: str) -> list[Finding]:
    return [f for f in findings if f.doc_id == doc_id]


@pytest.fixture
def repo(fixture_repo: Callable[[str], Path]) -> Path:
    return fixture_repo("soft-lifecycle")


def test_good_accepted_rfc_is_silent(repo: Path) -> None:
    findings = _findings(repo)
    assert _by_doc(findings, "0001-good") == []


def test_no_followups_field_warns(repo: Path) -> None:
    findings = _by_doc(_findings(repo), "0002-no-followups-field")
    assert len(findings) == 1
    assert "no `followups` field" in findings[0].message


def test_missing_followup_path_warns(repo: Path) -> None:
    findings = _by_doc(_findings(repo), "0003-missing-path")
    assert len(findings) == 1
    assert "does not exist in the graph" in findings[0].message


def test_missing_backlink_warns(repo: Path) -> None:
    findings = _by_doc(_findings(repo), "0004-no-backlink-adr")
    assert len(findings) == 1
    assert "does not link back" in findings[0].message


def test_broken_implements_warns(repo: Path) -> None:
    findings = _by_doc(_findings(repo), "broken-implements")
    assert len(findings) == 1
    assert "does not match any doc" in findings[0].message


def test_stale_planned_claim_warns(repo: Path) -> None:
    findings = _by_doc(_findings(repo), "stale-claim")
    assert len(findings) == 1
    assert findings[0].category == "stale-claim"
    assert "is now accepted" in findings[0].message
