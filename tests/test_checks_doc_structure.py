"""Tests for DuplicateBlockCheck."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

import pytest

from irminsul.checks.base import Finding
from irminsul.checks.duplicate_block import DuplicateBlockCheck

from .conftest import run_check, write_config


@pytest.fixture
def repo(fixture_repo: Callable[[str], Path]) -> Path:
    return fixture_repo("soft-doc-structure")


def _lines_flagged(repo: Path, findings: list[Finding], rel: str) -> list[str]:
    text = (repo / rel).read_text(encoding="utf-8").splitlines()
    return [text[f.line - 1] for f in findings if f.path and f.path.as_posix() == rel and f.line]


def test_repeated_list_item_is_reported_at_second_occurrence(repo: Path) -> None:
    findings = run_check(DuplicateBlockCheck, repo)

    assert len(findings) == 1
    assert findings[0].code == "duplicate-block/repeated-block"
    assert findings[0].line == 12
    assert "line 10" in findings[0].message


def test_short_repeats_and_fenced_copies_are_ignored(repo: Path) -> None:
    findings = run_check(DuplicateBlockCheck, repo)
    assert not [f for f in findings if f.line != 12]


def test_a_block_copied_into_another_live_doc_is_reported_once(tmp_path: Path) -> None:
    write_config(tmp_path)
    shared = "Source discovery walks every configured root and skips paths the ignore list names.\n"
    for rel, status in (
        ("guides/a.md", "stable"),
        ("guides/b.md", "stable"),
        ("guides/c.md", "draft"),
    ):
        doc = tmp_path / "docs" / rel
        doc.parent.mkdir(parents=True, exist_ok=True)
        doc.write_text(
            f"---\nid: {doc.stem}\ntitle: T\nstatus: {status}\n---\n\n# T\n\n{shared}",
            encoding="utf-8",
        )
    findings = run_check(DuplicateBlockCheck, tmp_path)
    assert [(f.code, f.path.as_posix()) for f in findings] == [
        ("duplicate-block/copied-block", "docs/guides/b.md")
    ]
    assert findings[0].data["first"] == "docs/guides/a.md:9"


def test_a_paragraph_repeated_under_another_heading_is_reported(tmp_path: Path) -> None:
    """A heading ends a block; it does not scope the comparison. Two sections restating
    one paragraph are exactly the pair that drifts apart, so narrowing this check to
    within-a-section would drop the case it is most useful for."""
    write_config(tmp_path)
    shared = "Source discovery walks every configured root and skips paths the ignore list names."
    doc = tmp_path / "docs" / "guides" / "a.md"
    doc.parent.mkdir(parents=True, exist_ok=True)
    doc.write_text(
        f"---\nid: a\ntitle: T\nstatus: stable\n---\n\n# T\n\n## Walking\n\n{shared}\n\n"
        f"## Ignoring\n\n{shared}\n",
        encoding="utf-8",
    )

    findings = run_check(DuplicateBlockCheck, tmp_path)

    assert [f.code for f in findings] == ["duplicate-block/repeated-block"]
    assert findings[0].line == 15


_RFC_TWO_SCENARIOS = """---
id: r
title: R
status: draft
---

# R

## Requirements

### Requirement: Exit codes
ID: exit-codes
Provenance: code

The run SHALL exit 2 when the invocation is wrong.

#### Scenario: Unknown flag
- **WHEN** {first_when}
- **THEN** the run exits 2 and prints the usage line on stderr so a script can tell a refusal from a bad call

#### Scenario: Missing argument
- **WHEN** {second_when}
- **THEN** the run exits 2 and prints the usage line on stderr so a script can tell a refusal from a bad call
"""


def _scenario_rfc(tmp_path: Path, *, first_when: str, second_when: str) -> list[Finding]:
    write_config(tmp_path)
    doc = tmp_path / "docs" / "rfcs" / "r.md"
    doc.parent.mkdir(parents=True, exist_ok=True)
    doc.write_text(
        _RFC_TWO_SCENARIOS.format(first_when=first_when, second_when=second_when),
        encoding="utf-8",
    )
    return run_check(DuplicateBlockCheck, tmp_path)


def test_scenarios_that_share_an_outcome_are_not_repeats(tmp_path: Path) -> None:
    """The requirement grammar puts a scenario's WHEN and THEN in two list items, and the
    scenarios of one requirement often end the same way; the THEN item alone was reported as
    a repeated block, with the advice to delete a scenario."""
    findings = _scenario_rfc(
        tmp_path,
        first_when="the user passes a flag the command does not take",
        second_when="the user omits an argument the command requires",
    )

    assert findings == []


def test_a_whole_scenario_copied_is_still_a_repeat(tmp_path: Path) -> None:
    when = "the user passes a flag the command does not take"

    findings = _scenario_rfc(tmp_path, first_when=when, second_when=when)

    assert [f.code for f in findings] == ["duplicate-block/repeated-block"]
    assert findings[0].line == 22
    assert "line 18" in findings[0].message
