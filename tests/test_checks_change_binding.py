"""Tests for ChangeBindingCheck (RFC-0029)."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

import pytest

from irminsul.checks.base import Finding, Severity
from irminsul.checks.change_binding import ChangeBindingCheck
from irminsul.config import find_config, load
from irminsul.docgraph import build_graph


def _findings(repo: Path, *, diff: frozenset[str] | None = None) -> list[Finding]:
    config = load(find_config(repo))
    graph = build_graph(repo, config, diff_changed_paths=diff)
    return ChangeBindingCheck().run(graph)


def _by_category(findings: list[Finding], category: str) -> list[Finding]:
    return [f for f in findings if f.category == category]


@pytest.fixture
def repo(fixture_repo: Callable[[str], Path]) -> Path:
    return fixture_repo("soft-change-binding")


def test_shape_missing_affects_on_accepted(repo: Path) -> None:
    findings = _findings(repo)
    matched = _by_category(findings, "missing-affects")
    assert len(matched) == 1
    assert matched[0].doc_id == "0002-accepted-missing-affects"
    assert matched[0].severity == Severity.warning


def test_shape_unknown_component(repo: Path) -> None:
    findings = _findings(repo)
    matched = _by_category(findings, "unknown-component")
    assert len(matched) == 1
    assert matched[0].doc_id == "0003-draft-unknown-component"
    assert "'ghost'" in matched[0].message


def test_shape_declared_scope_is_silent(repo: Path) -> None:
    findings = _findings(repo)
    assert all(f.doc_id != "0001-accepted-good" for f in findings)


def test_no_diff_no_binding_findings(repo: Path) -> None:
    findings = _findings(repo)
    assert _by_category(findings, "touched-but-undeclared") == []
    assert _by_category(findings, "declared-but-untouched") == []


def test_diff_within_declared_scope_is_silent(repo: Path) -> None:
    findings = _findings(repo, diff=frozenset({"app/auth/login.py"}))
    assert _by_category(findings, "touched-but-undeclared") == []
    assert _by_category(findings, "declared-but-untouched") == []


def test_diff_outside_declared_scope_warns(repo: Path) -> None:
    findings = _findings(repo, diff=frozenset({"app/billing/invoice.py"}))
    undeclared = _by_category(findings, "touched-but-undeclared")
    assert len(undeclared) == 1
    assert "'billing'" in undeclared[0].message
    assert undeclared[0].severity == Severity.warning

    untouched = _by_category(findings, "declared-but-untouched")
    assert len(untouched) == 1
    assert untouched[0].doc_id == "0001-accepted-good"
    assert "'auth'" in untouched[0].message
    assert untouched[0].severity == Severity.info


def test_deleted_source_outside_declared_scope_warns(repo: Path) -> None:
    (repo / "app" / "billing" / "invoice.py").unlink()
    findings = _findings(repo, diff=frozenset({"app/billing/invoice.py"}))
    undeclared = _by_category(findings, "touched-but-undeclared")
    assert len(undeclared) == 1
    assert "'billing'" in undeclared[0].message
    assert "app/billing/invoice.py" in undeclared[0].message


def test_deleted_source_inside_declared_scope_is_silent(repo: Path) -> None:
    (repo / "app" / "auth" / "session.py").unlink()
    findings = _findings(repo, diff=frozenset({"app/auth/session.py"}))
    assert _by_category(findings, "touched-but-undeclared") == []
    assert _by_category(findings, "declared-but-untouched") == []


def test_diff_covering_both_components(repo: Path) -> None:
    findings = _findings(repo, diff=frozenset({"app/auth/login.py", "app/billing/invoice.py"}))
    undeclared = _by_category(findings, "touched-but-undeclared")
    assert [f.doc_id for f in undeclared] == ["billing"]
    assert _by_category(findings, "declared-but-untouched") == []


def test_no_accepted_rfc_suppresses_binding_findings(repo: Path) -> None:
    for name in ("0001-accepted-good", "0002-accepted-missing-affects"):
        path = repo / "docs" / "80-evolution" / "rfcs" / f"{name}.md"
        text = path.read_text(encoding="utf-8")
        text = text.replace("rfc_state: accepted", "rfc_state: draft")
        text = text.replace("resolved_by: docs/50-decisions/0001-adr.md\n", "")
        path.write_text(text, encoding="utf-8")

    findings = _findings(repo, diff=frozenset({"app/billing/invoice.py"}))
    assert _by_category(findings, "touched-but-undeclared") == []
    assert _by_category(findings, "declared-but-untouched") == []


def test_draft_may_omit_affects(repo: Path) -> None:
    path = repo / "docs" / "80-evolution" / "rfcs" / "0004-draft-ready.md"
    text = path.read_text(encoding="utf-8")
    text = text.replace("affects:\n  - auth\n", "")
    path.write_text(text, encoding="utf-8")

    findings = _findings(repo)
    assert all(f.doc_id != "0004-draft-ready" for f in findings)
