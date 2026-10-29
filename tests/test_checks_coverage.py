"""Tests for CoverageCheck."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from irminsul.checks import Severity
from irminsul.checks.coverage import CoverageCheck

from .conftest import load_graph, run_check, write_config


def _run(repo: Path) -> list:
    return run_check(CoverageCheck, repo)


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
    findings = run_check(CoverageCheck, repo)
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


def test_a_missing_owned_test_is_reported_once(tmp_path: Path) -> None:
    """An `owns_tests:` entry is test-ownership's to resolve, the way the walk spells it.
    Coverage reading it too, as the default recommendation, reported one missing file
    twice."""
    from irminsul.checks.owned_tests import TestOwnershipCheck

    repo = tmp_path / "r"
    (repo / "src").mkdir(parents=True)
    (repo / "tests").mkdir()
    (repo / "src" / "thing.py").write_text("x = 1\n", encoding="utf-8")
    write_config(repo, source_roots=["src"])
    (repo / "docs" / "components").mkdir(parents=True)
    (repo / "docs" / "components" / "thing.md").write_text(
        "---\nid: thing\ntitle: Thing\nstatus: stable\ndescribes:\n  - src/thing.py\n"
        "owns_tests:\n  - tests/test_gone.py\n---\n\n# Thing\n\n## Scope & Limitations\n\nNone.\n",
        encoding="utf-8",
    )
    graph = load_graph(repo)

    codes = [f.code for f in CoverageCheck().run(graph) + TestOwnershipCheck().run(graph)]

    assert codes == ["test-ownership/owned-test-missing"]
