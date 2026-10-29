"""Tests for ChangeBindingCheck."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

import pytest

from irminsul.checks.base import Finding, Severity
from irminsul.checks.change_binding import ChangeBindingCheck
from irminsul.config import find_config, load
from irminsul.docgraph import build_graph

from .conftest import check_codes, commit_all, seed_repo


def _findings(repo: Path) -> list[Finding]:
    graph = build_graph(repo, load(find_config(repo)))
    return ChangeBindingCheck().run(graph)


def _by_kind(findings: list[Finding], kind: str) -> list[Finding]:
    return [f for f in findings if f.code == f"change-binding/{kind}"]


@pytest.fixture
def repo(fixture_repo: Callable[[str], Path]) -> Path:
    return fixture_repo("soft-change-binding")


def test_shape_missing_affects_on_accepted(repo: Path) -> None:
    findings = _findings(repo)
    matched = _by_kind(findings, "missing-affects")
    assert len(matched) == 1
    assert matched[0].doc_id == "0002-accepted-missing-affects"
    assert matched[0].severity == Severity.error


def test_shape_unknown_component(repo: Path) -> None:
    findings = _findings(repo)
    matched = _by_kind(findings, "unknown-component")
    assert len(matched) == 1
    assert matched[0].doc_id == "0003-draft-unknown-component"
    assert "'ghost'" in matched[0].message


def test_shape_declared_scope_is_silent(repo: Path) -> None:
    findings = _findings(repo)
    assert all(f.doc_id != "0001-accepted-good" for f in findings)


def test_a_diff_touching_an_undeclared_component_reports_only_the_shape_codes(repo: Path) -> None:
    """Which RFC a change is for is not something the tree can say, so `check --diff` does not
    compare the change with the accepted RFCs' `affects`; `change verify` and `change finalize`
    do, against the one RFC they are given."""
    base = seed_repo(repo)
    invoice = repo / "app" / "billing" / "invoice.py"
    invoice.write_text(invoice.read_text(encoding="utf-8") + "\nEDITED = True\n", encoding="utf-8")
    commit_all(repo, "touch billing")

    codes = check_codes(repo, "--diff", base, "--no-baseline")

    assert {code for code in codes if code.startswith("change-binding/")} == {
        "change-binding/missing-affects",
        "change-binding/unknown-component",
    }


def test_draft_may_omit_affects(repo: Path) -> None:
    path = repo / "docs" / "rfcs" / "0004-draft-ready.md"
    text = path.read_text(encoding="utf-8")
    text = text.replace("affects:\n  - auth\n", "")
    path.write_text(text, encoding="utf-8")

    findings = _findings(repo)
    assert all(f.doc_id != "0004-draft-ready" for f in findings)
