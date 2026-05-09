"""Tests for LiarCheck."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from irminsul.checks import Severity
from irminsul.checks.liar import LiarCheck
from irminsul.config import load
from irminsul.docgraph import build_graph


def _run(repo: Path) -> list:
    cfg = load(repo / "irminsul.toml")
    graph = build_graph(repo, cfg)
    return LiarCheck().run(graph)


def test_good_fixture_has_no_liar_findings(
    fixture_repo: Callable[[str], Path],
) -> None:
    findings = _run(fixture_repo("good"))
    assert findings == []


def test_t3_duplicating_t1_fields_flagged(
    fixture_repo: Callable[[str], Path],
) -> None:
    findings = _run(fixture_repo("bad-liar"))
    liar_findings = [f for f in findings if f.path and "widget.md" in f.path.as_posix()]
    assert len(liar_findings) >= 1
    assert all(f.severity == Severity.warning for f in liar_findings)


def test_findings_have_line_numbers(
    fixture_repo: Callable[[str], Path],
) -> None:
    findings = _run(fixture_repo("bad-liar"))
    liar_findings = [f for f in findings if f.path and "widget.md" in f.path.as_posix()]
    assert all(f.line is not None and f.line > 0 for f in liar_findings)


def test_t1_reference_doc_not_flagged(
    fixture_repo: Callable[[str], Path],
) -> None:
    findings = _run(fixture_repo("bad-liar"))
    ref_findings = [f for f in findings if f.path and "40-reference" in f.path.as_posix()]
    assert ref_findings == []
