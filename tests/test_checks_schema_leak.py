"""Tests for the SchemaLeakCheck."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from irminsul.checks import Severity
from irminsul.checks.schema_leak import SchemaLeakCheck
from irminsul.config import load
from irminsul.docgraph import build_graph


def _run(repo: Path) -> list:
    cfg = load(repo / "irminsul.toml")
    graph = build_graph(repo, cfg)
    return SchemaLeakCheck().run(graph)


def test_good_fixture_has_no_schema_leak_findings(
    fixture_repo: Callable[[str], Path],
) -> None:
    findings = _run(fixture_repo("good"))
    assert findings == []


def test_bad_schema_leak_flags_class_in_components(
    fixture_repo: Callable[[str], Path],
) -> None:
    findings = _run(fixture_repo("bad-schema-leak"))
    error_findings = [f for f in findings if f.severity == Severity.error]
    leaky_findings = [f for f in error_findings if f.path and "leaky.md" in f.path.as_posix()]

    # Should flag at least the Pydantic class line and the TS interface line.
    assert len(leaky_findings) >= 2
    # Each leaky finding has a line number pointing into the doc body.
    assert all(f.line is not None and f.line > 0 for f in leaky_findings)


def test_bad_schema_leak_does_not_flag_reference_layer(
    fixture_repo: Callable[[str], Path],
) -> None:
    """40-reference/schema/thing.md contains the same class def, but lives
    outside the protected glob — must NOT be flagged."""
    findings = _run(fixture_repo("bad-schema-leak"))
    reference_findings = [f for f in findings if f.path and "40-reference" in f.path.as_posix()]
    assert reference_findings == []


def test_bad_schema_leak_ignores_toml_fenced_block(
    fixture_repo: Callable[[str], Path],
) -> None:
    """A ```toml fenced block in leaky.md mentions `class` and `interface` —
    fence-aware scanning should skip it."""
    findings = _run(fixture_repo("bad-schema-leak"))
    messages = [f.message for f in findings]
    # The toml block has `class = "ok"` which should never trigger a finding.
    # Hard to assert exactly which line was skipped, but we can assert the
    # total count corresponds only to the python+ts blocks (2 findings),
    # not 3+.
    leaky_count = len([f for f in findings if f.path and "leaky.md" in f.path.as_posix()])
    assert leaky_count == 2, f"expected 2 findings, got {leaky_count}: {messages}"
