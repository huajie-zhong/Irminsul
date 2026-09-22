"""Tests for BoundaryCheck."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from irminsul.checks import Severity
from irminsul.checks.boundary import BoundaryCheck
from irminsul.config import load
from irminsul.docgraph import build_graph


def _run(repo: Path) -> list:
    cfg = load(repo / "irminsul.toml")
    graph = build_graph(repo, cfg)
    return BoundaryCheck().run(graph)


def test_good_fixture_has_no_boundary_findings(
    fixture_repo: Callable[[str], Path],
) -> None:
    findings = _run(fixture_repo("good"))
    assert findings == []


def test_missing_scope_section_flagged(
    fixture_repo: Callable[[str], Path],
) -> None:
    findings = _run(fixture_repo("soft-boundary"))
    assert len(findings) == 1
    assert findings[0].severity == Severity.error
    assert "Scope & Limitations" in findings[0].message


def test_finding_has_path(
    fixture_repo: Callable[[str], Path],
) -> None:
    findings = _run(fixture_repo("soft-boundary"))
    assert findings[0].path is not None
    assert "widget.md" in findings[0].path.as_posix()


_STABLE_DOC = """---
id: alpha
title: "Alpha"
status: stable
describes: []
---

# Alpha

It does arithmetic.

## Scope & Limitations
{section}
"""


def _one_doc(tmp_path: Path, section: str) -> list:
    repo = tmp_path / "r"
    (repo / "docs" / "components").mkdir(parents=True)
    (repo / "irminsul.toml").write_text(
        'project_name = "r"\n[paths]\ndocs_root = "docs"\nsource_roots = []\n'
        '[checks]\nenabled = ["boundary"]\n',
        encoding="utf-8",
    )
    (repo / "docs" / "components" / "alpha.md").write_text(
        _STABLE_DOC.format(section=section), encoding="utf-8"
    )
    return _run(repo)


def test_a_section_holding_only_the_scaffold_prompt_is_unfilled(tmp_path: Path) -> None:
    """`irminsul new component` writes the prompt, `context` reads the section back to an
    agent as what the component does not do, and nothing used to notice the difference."""
    findings = _one_doc(tmp_path, "<!-- Describe what this component does NOT do. -->")

    assert [f.code for f in findings] == ["boundary/unfilled-scope-section"]
    assert findings[0].severity is Severity.error  # the doc is stable, so it blocks


def test_an_empty_section_is_unfilled(tmp_path: Path) -> None:
    assert [f.code for f in _one_doc(tmp_path, "")] == ["boundary/unfilled-scope-section"]


def test_an_answered_section_is_not_reported(tmp_path: Path) -> None:
    assert _one_doc(tmp_path, "It does not persist anything.") == []


def test_a_prompt_answered_beside_the_comment_is_enough(tmp_path: Path) -> None:
    """The comment may be left in place; what matters is that something else is there."""
    section = "<!-- Describe what this component does NOT do. -->\nIt does not persist."
    assert _one_doc(tmp_path, section) == []


def test_prose_under_a_later_section_does_not_stand_in(tmp_path: Path) -> None:
    section = "<!-- prompt -->\n\n## Notes\n\nPlenty of prose, but not a boundary."
    assert [f.code for f in _one_doc(tmp_path, section)] == ["boundary/unfilled-scope-section"]


def test_an_adjacent_next_heading_does_not_stand_in(tmp_path: Path) -> None:
    """No blank line between the empty scope heading and the next one. The section-break
    matcher wanted a preceding newline, so a heading that *starts* the remainder was missed
    and the following section's prose counted as the answer."""
    section = "## Notes\n\nPlenty of prose, but not a boundary."
    assert [f.code for f in _one_doc(tmp_path, section)] == ["boundary/unfilled-scope-section"]


def test_a_tab_separated_next_heading_does_not_stand_in(tmp_path: Path) -> None:
    section = "<!-- prompt -->\n\n##\tNotes\n\nPlenty of prose, but not a boundary."
    assert [f.code for f in _one_doc(tmp_path, section)] == ["boundary/unfilled-scope-section"]
