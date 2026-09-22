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
    assert "recommends no tests" in findings[0].message


def test_nonexistent_test_path_flagged(
    fixture_repo: Callable[[str], Path],
    tmp_path: Path,
) -> None:
    import shutil

    repo = shutil.copytree(
        Path(__file__).parent / "fixtures" / "repos" / "good-coverage",
        tmp_path / "repo",
    )
    doc = repo / "docs" / "components" / "thing.md"
    content = doc.read_text(encoding="utf-8")
    doc.write_text(
        content.replace("tests/test_thing.py", "tests/nonexistent.py"),
        encoding="utf-8",
    )
    cfg = load(repo / "irminsul.toml")
    graph = build_graph(repo, cfg)
    findings = CoverageCheck().run(graph)
    assert len(findings) == 1
    assert "matches no file" in findings[0].message


def test_a_malformed_recommendation_is_a_finding_not_a_traceback(tmp_path: Path) -> None:
    """`Path.glob` raises on input a person can type — an absolute pattern is
    NotImplementedError, `a**b/*.py` is ValueError — and neither was caught, so one
    mistyped entry ended the whole run instead of producing a finding."""
    from irminsul.checks.coverage import _resolves

    for entry in ("/abs/*.py", "a**b/*.py", "tests/[z-a].py"):
        assert _resolves(tmp_path, entry) is False


def test_a_glob_resolves_the_way_the_shared_matcher_matches(tmp_path: Path) -> None:
    """The two readings disagreed: `test_*.py` matched `tests/test_a.py` for footprint and
    context while coverage called the entry dead."""
    from irminsul.checks.coverage import _resolves
    from irminsul.declared_tests import matching_paths

    (tmp_path / "tests").mkdir()
    (tmp_path / "tests" / "test_a.py").write_text("x = 1\n", encoding="utf-8")

    for entry in ("tests/test_*.py", "tests/", "tests/test_a.py"):
        matched = bool(matching_paths([entry], ["tests/test_a.py"]))
        assert _resolves(tmp_path, entry) == matched, entry
