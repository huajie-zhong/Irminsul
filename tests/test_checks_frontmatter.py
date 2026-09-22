"""Tests for the FrontmatterCheck."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from irminsul.checks import Severity
from irminsul.checks.frontmatter import FrontmatterCheck
from irminsul.config import load
from irminsul.docgraph import build_graph


def _run(repo: Path) -> list:
    cfg = load(repo / "irminsul.toml")
    graph = build_graph(repo, cfg)
    return FrontmatterCheck().run(graph)


def test_good_fixture_has_no_frontmatter_findings(
    fixture_repo: Callable[[str], Path],
) -> None:
    findings = _run(fixture_repo("good"))
    assert findings == []


def test_bad_frontmatter_fixture_reports_each_failure_mode(
    fixture_repo: Callable[[str], Path],
) -> None:
    findings = _run(fixture_repo("bad-frontmatter"))
    messages = [f.message for f in findings]

    # Every finding from this check is severity=error.
    assert all(f.severity == Severity.error for f in findings)
    # Parse error for bad-status (validation failure).
    assert any("parse error" in m and "status" in m for m in messages)
    # Parse error for missing-title.
    assert any("parse error" in m and "title" in m for m in messages)
    # Missing-frontmatter file.
    assert any("missing frontmatter" in m for m in messages)
    # ID/filename mismatch.
    assert any("does not match filename" in m for m in messages)


def _doc_repo(tmp_path: Path, frontmatter: str) -> Path:
    repo = tmp_path / "r"
    (repo / "docs" / "components").mkdir(parents=True)
    (repo / "irminsul.toml").write_text(
        'project_name = "r"\n[paths]\ndocs_root = "docs"\nsource_roots = ["src"]\n',
        encoding="utf-8",
    )
    (repo / "docs" / "components" / "alpha.md").write_text(
        f"---\nid: alpha\ntitle: Alpha\nstatus: stable\n{frontmatter}---\n\n# Alpha\n",
        encoding="utf-8",
    )
    return repo


def _misspelled(repo: Path) -> list:
    return [f for f in _run(repo) if f.code == "frontmatter/misspelled-field"]


def test_a_misspelled_canonical_field_is_an_error(tmp_path: Path) -> None:
    """`desribes` was accepted as a project key, so the doc claimed nothing and every
    check that reads `describes` went quiet about it."""
    repo = _doc_repo(tmp_path, "desribes:\n  - src/a.py\n")

    findings = _misspelled(repo)

    assert len(findings) == 1
    assert findings[0].severity == Severity.error
    assert findings[0].line == 5
    assert findings[0].data == {
        "problem": "misspelled-field",
        "field": "desribes",
        "expected": "describes",
    }


def test_near_misses_in_case_and_separator_are_caught(tmp_path: Path) -> None:
    repo = _doc_repo(tmp_path, "depends-on:\n  - beta\nTests:\n  - tests/test_a.py\n")

    assert sorted(f.data["expected"] for f in _misspelled(repo)) == ["depends_on", "tests"]


def test_a_project_key_unlike_any_field_is_left_alone(tmp_path: Path) -> None:
    repo = _doc_repo(tmp_path, "owner: platform-team\nlayout: page\n")

    assert _misspelled(repo) == []


def test_a_near_miss_beside_the_real_field_is_left_alone(tmp_path: Path) -> None:
    """With `tests` set too, `test` is not standing in for it."""
    repo = _doc_repo(tmp_path, "tests:\n  - tests/test_a.py\ntest: smoke\n")

    assert _misspelled(repo) == []
