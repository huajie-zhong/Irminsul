"""Tests for the FrontmatterCheck."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

import pytest

from irminsul.checks import Severity
from irminsul.checks.frontmatter import FrontmatterCheck

from .conftest import load_graph, run_check, write_config


def _run(repo: Path) -> list:
    return run_check(FrontmatterCheck, repo)


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
    write_config(repo, source_roots=["src"])
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
        "field": "desribes",
        "expected": "describes",
    }


def test_near_misses_in_case_and_separator_are_caught(tmp_path: Path) -> None:
    repo = _doc_repo(tmp_path, "depends-on:\n  - beta\nOwns-Tests:\n  - tests/test_a.py\n")

    assert sorted(f.data["expected"] for f in _misspelled(repo)) == ["depends_on", "owns_tests"]


def test_a_project_key_unlike_any_field_is_left_alone(tmp_path: Path) -> None:
    repo = _doc_repo(tmp_path, "owner: platform-team\nlayout: page\n")

    assert _misspelled(repo) == []


def test_a_near_miss_beside_the_real_field_is_left_alone(tmp_path: Path) -> None:
    """With `owns_tests` set too, `owns_test` is not standing in for it."""
    repo = _doc_repo(tmp_path, "owns_tests:\n  - tests/test_a.py\nowns_test: smoke\n")

    assert _misspelled(repo) == []


def _retired(repo: Path) -> list:
    return [f for f in _run(repo) if f.code == "frontmatter/retired-field"]


@pytest.mark.parametrize(
    ("key", "value", "replacement"),
    [
        ("tests", "\n  - tests/test_a.py", "recommended_tests"),
        ("requires_env", "\n  - API_KEY", "env-vars"),
        ("superseded_by", " beta", "supersedes"),
    ],
)
def test_a_retired_key_is_an_error_that_names_its_replacement(
    tmp_path: Path, key: str, value: str, replacement: str
) -> None:
    """Ignored silently, a doc that still sets `tests` would read as recommending tests
    while recommending none."""
    repo = _doc_repo(tmp_path, f"{key}:{value}\n")

    findings = _retired(repo)

    assert len(findings) == 1
    assert findings[0].severity == Severity.error
    assert findings[0].line == 5
    assert findings[0].data == {"field": key}
    assert replacement in (findings[0].suggestion or "")
    assert "alpha" in load_graph(repo).nodes


def test_a_project_key_is_not_a_retired_one(tmp_path: Path) -> None:
    repo = _doc_repo(tmp_path, "owner: platform-team\n")

    assert _retired(repo) == []


def test_a_retired_inventory_key_is_reported_and_the_doc_still_loads(tmp_path: Path) -> None:
    """An inventory entry refuses unknown keys, so a retired one there used to fail the
    schema: the doc left the graph and no finding could name what replaced the key."""
    repo = _doc_repo(
        tmp_path,
        "inventory:\n  - kind: cli\n    items: [alpha]\n    fingerprints:\n      alpha: dead00\n",
    )

    findings = _retired(repo)

    assert [f.data for f in findings] == [{"field": "inventory.fingerprints"}]
    assert findings[0].line == 8
    assert "anchor" in (findings[0].suggestion or "")
    graph = load_graph(repo)
    assert graph.nodes["alpha"].frontmatter.inventory[0].items == ["alpha"]


def _missing_summary(repo: Path) -> list:
    return [f for f in _run(repo) if f.code == "frontmatter/missing-summary"]


def test_a_doc_without_a_summary_is_reported_and_still_loads(tmp_path: Path) -> None:
    repo = _doc_repo(tmp_path, "")

    findings = _missing_summary(repo)

    assert [(f.doc_id, f.severity) for f in findings] == [("alpha", Severity.error)]
    assert "alpha" in load_graph(repo).nodes
    assert _missing_summary(_doc_repo(tmp_path / "s", "summary: One line.\n")) == []


def test_a_sealed_rfc_is_not_asked_for_a_summary(tmp_path: Path) -> None:
    """An implemented RFC cannot change, so it could never answer the finding."""
    repo = _doc_repo(tmp_path, "summary: One line.\n")
    rfcs = repo / "docs" / "rfcs"
    rfcs.mkdir()
    for slug, state in (("done", "implemented"), ("open", "draft")):
        (rfcs / f"{slug}.md").write_text(
            f"---\nid: {slug}\ntitle: T\nstatus: draft\nrfc_state: {state}\n"
            "resolved_by: docs/components/alpha.md\n---\n\n# T\n",
            encoding="utf-8",
        )

    assert [(f.doc_id, f.severity) for f in _missing_summary(repo)] == [("open", Severity.warning)]


def _missing_frontmatter(repo: Path) -> list:
    return [f for f in _run(repo) if f.code == "frontmatter/missing-frontmatter"]


def test_a_doc_without_frontmatter_inside_a_layer_is_told_to_add_it(tmp_path: Path) -> None:
    repo = _doc_repo(tmp_path, "summary: One line.\n")
    (repo / "docs" / "components" / "bare.md").write_text("# Bare\n", encoding="utf-8")

    (finding,) = _missing_frontmatter(repo)

    assert finding.suggestion is not None
    assert "`id: bare`" in finding.suggestion
    assert "irminsul new" in finding.suggestion
    assert "move" not in finding.suggestion


def test_a_doc_without_frontmatter_outside_every_layer_is_also_told_to_move(
    tmp_path: Path,
) -> None:
    repo = _doc_repo(tmp_path, "summary: One line.\n")
    (repo / "docs" / "usage.md").write_text("# Usage\n", encoding="utf-8")

    (finding,) = _missing_frontmatter(repo)

    assert finding.suggestion is not None
    assert "`id: usage`" in finding.suggestion
    assert "outside every layer folder" in finding.suggestion
    assert "`docs/guides/`" in finding.suggestion
    assert "irminsul refs docs/usage.md" in finding.suggestion
