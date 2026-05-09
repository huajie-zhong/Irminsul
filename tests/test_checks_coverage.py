"""Tests for CoverageCheck."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from irminsul.checks import Severity
from irminsul.checks.coverage import CoverageCheck
from irminsul.config import load
from irminsul.docgraph import build_graph


def _run(repo: Path) -> list:
    cfg = load(repo / "irminsul.toml")
    graph = build_graph(repo, cfg)
    return CoverageCheck().run(graph)


def test_good_coverage_fixture_has_no_findings(
    fixture_repo: Callable[[str], Path],
) -> None:
    findings = _run(fixture_repo("good-coverage"))
    assert findings == []


def test_good_fixture_passes_coverage(
    fixture_repo: Callable[[str], Path],
) -> None:
    findings = _run(fixture_repo("good"))
    assert findings == []


def test_missing_tests_field_flagged(
    fixture_repo: Callable[[str], Path],
) -> None:
    findings = _run(fixture_repo("bad-coverage"))
    assert len(findings) == 1
    assert findings[0].severity == Severity.error
    assert "tests:" in findings[0].message


def test_nonexistent_test_path_flagged(
    fixture_repo: Callable[[str], Path],
    tmp_path: Path,
) -> None:
    import shutil

    repo = shutil.copytree(
        Path(__file__).parent / "fixtures" / "repos" / "good-coverage",
        tmp_path / "repo",
    )
    doc = repo / "docs" / "20-components" / "thing.md"
    content = doc.read_text(encoding="utf-8")
    doc.write_text(
        content.replace("tests/test_thing.py", "tests/nonexistent.py"),
        encoding="utf-8",
    )
    cfg = load(repo / "irminsul.toml")
    graph = build_graph(repo, cfg)
    findings = CoverageCheck().run(graph)
    assert len(findings) == 1
    assert "does not exist" in findings[0].message
