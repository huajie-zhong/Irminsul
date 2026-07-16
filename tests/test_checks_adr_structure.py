"""Tests for AdrStructureCheck (RFC 0023)."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

import pytest

from irminsul.checks.adr_structure import AdrStructureCheck
from irminsul.checks.base import Finding, Severity
from irminsul.config import find_config, load
from irminsul.docgraph import build_graph


def _findings(repo: Path) -> list[Finding]:
    config = load(find_config(repo))
    graph = build_graph(repo, config)
    return AdrStructureCheck().run(graph)


def _by_doc(findings: list[Finding], doc_id: str) -> list[Finding]:
    return [finding for finding in findings if finding.doc_id == doc_id]


@pytest.fixture
def repo(fixture_repo: Callable[[str], Path]) -> Path:
    return fixture_repo("soft-adr-structure")


def test_fully_structured_adr_is_silent(repo: Path) -> None:
    assert _by_doc(_findings(repo), "0001-good-adr") == []


def test_missing_status_section_warns(repo: Path) -> None:
    matched = _by_doc(_findings(repo), "0002-missing-status")
    assert len(matched) == 1
    assert matched[0].severity == Severity.warning
    assert matched[0].category == "missing-section"
    assert "## Status" in matched[0].message


def test_bare_adr_flags_each_missing_section(repo: Path) -> None:
    matched = _by_doc(_findings(repo), "0003-bare")
    assert {finding.message for finding in matched} == {
        "ADR is missing a '## Status' section",
        "ADR is missing a '## Alternatives Considered' section",
        "ADR is missing a '## Consequences' section",
    }


def test_heading_match_is_case_insensitive(repo: Path) -> None:
    assert _by_doc(_findings(repo), "0004-lowercase-alternatives") == []


def test_duplicate_required_section_warns_at_second_heading(repo: Path) -> None:
    matched = _by_doc(_findings(repo), "0005-duplicate-decision")
    assert len(matched) == 1
    assert matched[0].category == "duplicate-section"
    assert matched[0].line is not None


@pytest.mark.parametrize("doc_id", ["0006-empty-decision", "0007-placeholder-decision"])
def test_unreviewable_decision_warns(repo: Path, doc_id: str) -> None:
    matched = _by_doc(_findings(repo), doc_id)
    assert len(matched) == 1
    assert matched[0].category == "empty-decision"
    assert matched[0].line is not None


def test_fenced_headings_do_not_satisfy_required_sections(repo: Path) -> None:
    matched = _by_doc(_findings(repo), "0008-fenced-headings")
    assert {finding.category for finding in matched} == {"missing-section"}
    assert len(matched) == 5


def test_non_adr_doc_is_ignored(repo: Path) -> None:
    assert _by_doc(_findings(repo), "overview") == []
