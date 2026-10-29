"""Tests for AdrStructureCheck."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

import pytest

from irminsul.checks.adr_structure import AdrStructureCheck
from irminsul.checks.base import Finding, Severity

from .conftest import by_doc, run_check, write_config


def _findings(repo: Path) -> list[Finding]:
    return run_check(AdrStructureCheck, repo)


@pytest.fixture
def repo(fixture_repo: Callable[[str], Path]) -> Path:
    return fixture_repo("soft-adr-structure")


def test_fully_structured_adr_is_silent(repo: Path) -> None:
    assert by_doc(_findings(repo), "0001-good-adr") == []


def test_missing_status_section_is_an_error(repo: Path) -> None:
    matched = by_doc(_findings(repo), "0002-missing-status")
    assert len(matched) == 1
    assert matched[0].severity == Severity.error
    assert matched[0].code == "adr-structure/missing-section"
    assert "## Status" in matched[0].message


def test_bare_adr_flags_each_missing_section(repo: Path) -> None:
    matched = by_doc(_findings(repo), "0003-bare")
    assert {finding.message for finding in matched} == {
        "ADR is missing a '## Status' section",
        "ADR is missing a '## Alternatives Considered' section",
        "ADR is missing a '## Consequences' section",
    }


def test_heading_match_is_case_insensitive(repo: Path) -> None:
    assert by_doc(_findings(repo), "0004-lowercase-alternatives") == []


def test_duplicate_required_section_warns_at_second_heading(repo: Path) -> None:
    matched = by_doc(_findings(repo), "0005-duplicate-decision")
    assert len(matched) == 1
    assert matched[0].code == "adr-structure/duplicate-section"
    assert matched[0].line is not None


@pytest.mark.parametrize("doc_id", ["0006-empty-decision", "0007-placeholder-decision"])
def test_unreviewable_decision_warns(repo: Path, doc_id: str) -> None:
    matched = by_doc(_findings(repo), doc_id)
    assert len(matched) == 1
    assert matched[0].code == "adr-structure/empty-decision"
    assert matched[0].line is not None


def test_fenced_headings_do_not_satisfy_required_sections(repo: Path) -> None:
    matched = by_doc(_findings(repo), "0008-fenced-headings")
    assert {finding.code for finding in matched} == {"adr-structure/missing-section"}
    assert len(matched) == 5


def test_non_adr_doc_is_ignored(repo: Path) -> None:
    assert by_doc(_findings(repo), "overview") == []


def test_a_decision_is_not_judged_by_its_words(tmp_path: Path) -> None:
    """`TBD` was on a phrase list that read it as no decision. Whether a decision says
    enough is the reader's to judge; only a prompt the template marked is a placeholder."""
    repo = tmp_path / "r"
    (repo / "docs" / "decisions").mkdir(parents=True)
    write_config(repo)
    sections = "\n\n".join(
        f"## {name}\n\n{text}"
        for name, text in (
            ("Status", "Accepted."),
            ("Context", "Why."),
            ("Decision", "TBD."),
            ("Alternatives Considered", "None."),
            ("Consequences", "Some."),
        )
    )
    (repo / "docs" / "decisions" / "pick.md").write_text(
        f"---\nid: pick\ntitle: Pick\nstatus: stable\n---\n\n# Pick\n\n{sections}\n",
        encoding="utf-8",
    )

    assert by_doc(_findings(repo), "pick") == []
