"""Tests for the UniquenessCheck."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from irminsul.checks import Severity
from irminsul.checks.uniqueness import UniquenessCheck, specificity
from irminsul.config import load
from irminsul.docgraph import build_graph


def _run(repo: Path) -> list:
    cfg = load(repo / "irminsul.toml")
    graph = build_graph(repo, cfg)
    return UniquenessCheck().run(graph)


def test_specificity_ordering() -> None:
    # exact > narrower glob > broader glob
    exact = specificity("app/planner/routing/handler.py")
    narrow = specificity("app/planner/routing/*.py")
    broad = specificity("app/planner/**")
    assert exact > narrow > broad


def test_good_fixture_has_no_uniqueness_findings(
    fixture_repo: Callable[[str], Path],
) -> None:
    findings = _run(fixture_repo("good"))
    assert [f for f in findings if f.severity == Severity.error] == []


def test_specificity_fixture_resolves_cleanly(
    fixture_repo: Callable[[str], Path],
) -> None:
    """Parent claims app/planner/**, child claims app/planner/routing/*.py.
    Child wins on overlapping files; no tie."""
    findings = _run(fixture_repo("specificity"))
    error_findings = [f for f in findings if f.severity == Severity.error]
    assert error_findings == []


def test_bad_uniqueness_flags_tied_claims(
    fixture_repo: Callable[[str], Path],
) -> None:
    findings = _run(fixture_repo("bad-uniqueness"))
    error_findings = [f for f in findings if f.severity == Severity.error]
    error_messages = [f.message for f in error_findings]
    # Both composer-a.md and composer-b.md claim app/composer.py at identical
    # specificity → tie at most-specific level.
    assert any("app/composer.py" in m and "same specificity" in m for m in error_messages)
    assert any(f.path == Path("app/composer.py") for f in error_findings)


def test_bad_uniqueness_flags_unclaimed_in_covered_dir(
    fixture_repo: Callable[[str], Path],
) -> None:
    findings = _run(fixture_repo("bad-uniqueness"))
    warn_findings = [f for f in findings if f.severity == Severity.warning]
    warn_messages = [f.message for f in warn_findings]
    # app/stranger.py lives in covered dir `app/` but no doc claims it.
    assert any("app/stranger.py" in m for m in warn_messages)
    assert any(f.path == Path("app/stranger.py") for f in warn_findings)


def test_bad_uniqueness_skips_init_py(
    fixture_repo: Callable[[str], Path],
) -> None:
    findings = _run(fixture_repo("bad-uniqueness"))
    warn_messages = [f.message for f in findings if f.severity == Severity.warning]
    # __init__.py is on the omission skip list.
    assert not any("__init__.py" in m for m in warn_messages)
