"""Tests for RequirementGrammarCheck (RFC-0030)."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

import pytest

from irminsul.checks.base import Finding, Severity
from irminsul.checks.requirement_grammar import RequirementGrammarCheck
from irminsul.config import find_config, load
from irminsul.docgraph import build_graph


def _findings(repo: Path) -> list[Finding]:
    config = load(find_config(repo))
    graph = build_graph(repo, config)
    return RequirementGrammarCheck().run(graph)


def _categories(findings: list[Finding], doc_id: str) -> list[str]:
    return sorted(f.category or "" for f in findings if f.doc_id == doc_id)


@pytest.fixture
def repo(fixture_repo: Callable[[str], Path]) -> Path:
    return fixture_repo("soft-change-binding")


def test_well_formed_requirements_are_silent(repo: Path) -> None:
    findings = _findings(repo)
    assert _categories(findings, "0001-accepted-good") == []
    assert _categories(findings, "0004-draft-ready") == []


def test_disposition_is_silent(repo: Path) -> None:
    findings = _findings(repo)
    assert _categories(findings, "0007-draft-disposition") == []


def test_docs_without_section_are_silent(repo: Path) -> None:
    findings = _findings(repo)
    assert _categories(findings, "0003-draft-unknown-component") == []


def test_bad_grammar_categories(repo: Path) -> None:
    findings = _findings(repo)
    assert _categories(findings, "0005-draft-bad-grammar") == [
        "duplicate-id",
        "incomplete-scenario",
        "invalid-id",
        "invalid-provenance",
        "missing-behavior",
        "missing-id",
        "missing-provenance",
        "missing-scenario",
        "task-duplicate-id",
        "task-unresolved-component",
        "task-unresolved-req",
    ]
    assert all(
        f.severity == Severity.warning for f in findings if f.doc_id == "0005-draft-bad-grammar"
    )


def test_well_formed_tasks_are_silent(repo: Path) -> None:
    findings = _findings(repo)
    assert not [
        f
        for f in findings
        if (f.category or "").startswith("task-") and f.doc_id == "0001-accepted-good"
    ]


def test_task_unresolved_req_names_reference(repo: Path) -> None:
    findings = _findings(repo)
    [finding] = [
        f
        for f in findings
        if f.doc_id == "0005-draft-bad-grammar" and f.category == "task-unresolved-req"
    ]
    assert "'ghost-req'" in finding.message


def test_incomplete_scenario_names_missing_keyword(repo: Path) -> None:
    findings = _findings(repo)
    [incomplete] = [
        f
        for f in findings
        if f.doc_id == "0005-draft-bad-grammar" and f.category == "incomplete-scenario"
    ]
    assert "missing THEN" in incomplete.message
    assert "missing WHEN" not in incomplete.message


def test_mixed_disposition_flagged(repo: Path) -> None:
    findings = _findings(repo)
    assert "mixed-disposition" in _categories(findings, "0006-draft-mixed")


def test_findings_carry_lines(repo: Path) -> None:
    findings = _findings(repo)
    assert all(f.line is not None for f in findings if f.doc_id == "0005-draft-bad-grammar")
