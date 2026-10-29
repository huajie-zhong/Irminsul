"""Tests for RfcStructureCheck."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

import pytest

from irminsul.checks.base import Finding, Severity
from irminsul.checks.rfc_structure import RfcStructureCheck

from .conftest import by_doc, check_findings, run_check, write, write_config


def _findings(repo: Path) -> list[Finding]:
    return run_check(RfcStructureCheck, repo)


def _codes(findings: list[Finding]) -> list[str]:
    return sorted(finding.code for finding in findings)


def _line_of(repo: Path, doc_id: str, text: str) -> int:
    lines = (repo / "docs" / "rfcs" / f"{doc_id}.md").read_text(encoding="utf-8").splitlines()
    return next(number for number, line in enumerate(lines, start=1) if line.startswith(text))


@pytest.fixture
def repo(fixture_repo: Callable[[str], Path]) -> Path:
    return fixture_repo("soft-rfc-structure")


def test_a_large_rfc_in_the_two_part_layout_is_silent(repo: Path) -> None:
    assert by_doc(_findings(repo), "good-large") == []


def test_no_weight_is_reported(repo: Path) -> None:
    matched = by_doc(_findings(repo), "no-weight")

    assert _codes(matched) == ["rfc-structure/missing-weight"]
    assert matched[0].path == Path("docs/rfcs/no-weight.md")


def test_a_weight_other_than_small_or_large_is_reported(repo: Path) -> None:
    matched = by_doc(_findings(repo), "bad-weight")

    assert _codes(matched) == ["rfc-structure/missing-weight"]
    assert "medium" in matched[0].message


def test_a_small_rfc_without_a_problem_is_silent(repo: Path) -> None:
    assert by_doc(_findings(repo), "good-small") == []


def test_a_small_rfc_still_needs_its_summary_and_decisions(tmp_path: Path) -> None:
    write_config(tmp_path)
    write(
        tmp_path,
        "docs/rfcs/bare.md",
        "---\nid: bare\ntitle: Bare\nstatus: draft\ndescribes: []\nrfc_state: draft\n"
        "affects: []\nweight: small\n---\n\n# Bare\n\n## Design detail\n\nNames.\n",
    )

    matched = _findings(tmp_path)

    assert sorted(f.message for f in matched) == [
        "RFC is missing a '## Decisions' section its small weight requires",
        "RFC is missing a '## Summary' section its small weight requires",
    ]


def test_a_large_rfc_needs_all_five_owners_sections(tmp_path: Path) -> None:
    write_config(tmp_path)
    write(
        tmp_path,
        "docs/rfcs/thin.md",
        "---\nid: thin\ntitle: Thin\nstatus: draft\ndescribes: []\nrfc_state: draft\n"
        "affects: []\nweight: large\n---\n\n# Thin\n\n## Summary\n\nSays it.\n\n"
        "## Decisions\n\nNone.\n\n## Design detail\n\nNames.\n",
    )

    matched = _findings(tmp_path)

    assert _codes(matched) == ["rfc-structure/missing-section"] * 3
    assert sorted(f.message for f in matched) == [
        "RFC is missing a '## Cost and risk' section its large weight requires",
        "RFC is missing a '## How it works' section its large weight requires",
        "RFC is missing a '## Problem' section its large weight requires",
    ]


def test_decisions_holding_only_the_templates_comment_is_reported(repo: Path) -> None:
    matched = by_doc(_findings(repo), "empty-decisions")

    assert _codes(matched) == ["rfc-structure/missing-section"]
    assert "Decisions" in matched[0].message
    assert matched[0].severity is Severity.error


def test_a_marked_placeholder_in_an_owners_section_is_empty(tmp_path: Path) -> None:
    write_config(tmp_path)
    write(
        tmp_path,
        "docs/rfcs/marked.md",
        "---\nid: marked\ntitle: Marked\nstatus: draft\ndescribes: []\nrfc_state: draft\n"
        "affects: []\nweight: small\n---\n\n# Marked\n\n## Summary\n\nSays it.\n\n"
        "## Decisions\n\nThe options. <!-- irminsul:placeholder -->\n\n## Design detail\n\nNames.\n",
    )

    assert _codes(_findings(tmp_path)) == ["rfc-structure/missing-section"]


@pytest.mark.parametrize("doc_id", ["implemented-old-layout", "rejected-old-layout"])
def test_a_resolved_rfc_in_the_old_layout_is_not_judged(repo: Path, doc_id: str) -> None:
    assert by_doc(_findings(repo), doc_id) == []


def test_an_owners_section_below_design_detail_is_out_of_order(repo: Path) -> None:
    matched = by_doc(_findings(repo), "cost-moved-down")

    assert _codes(matched) == ["rfc-structure/section-out-of-order"]
    assert "Cost and risk" in matched[0].message
    assert matched[0].line == _line_of(repo, "cost-moved-down", "## Cost and risk")


def test_requirements_without_design_detail_is_out_of_order(repo: Path) -> None:
    matched = by_doc(_findings(repo), "no-design-detail")

    assert _codes(matched) == ["rfc-structure/section-out-of-order"]
    assert "Design detail" in matched[0].message
    assert matched[0].line == _line_of(repo, "no-design-detail", "## Requirements")


def test_a_draft_without_requirements_or_design_detail_is_not_out_of_order(
    tmp_path: Path,
) -> None:
    write_config(tmp_path)
    write(
        tmp_path,
        "docs/rfcs/stub.md",
        "---\nid: stub\ntitle: Stub\nstatus: draft\ndescribes: []\nrfc_state: draft\n"
        "affects: []\nweight: small\n---\n\n# Stub\n\n## Summary\n\nSays it.\n\n"
        "## Decisions\n\nNone.\n",
    )

    assert _findings(tmp_path) == []


def test_a_paragraph_of_claim_ids_in_how_it_works_is_a_hint(repo: Path) -> None:
    matched = by_doc(_findings(repo), "dense-owner")

    assert _codes(matched) == ["rfc-structure/dense-paragraph"]
    assert matched[0].severity is Severity.warning
    assert matched[0].line == _line_of(repo, "dense-owner", "The change touches")


def test_the_same_list_in_design_detail_is_silent(repo: Path) -> None:
    assert by_doc(_findings(repo), "dense-agent") == []


def test_each_list_item_is_its_own_paragraph(repo: Path) -> None:
    matched = by_doc(_findings(repo), "dense-list")

    assert _codes(matched) == ["rfc-structure/dense-paragraph"]
    assert matched[0].line == _line_of(repo, "dense-list", "- The third item")


def _summary_paragraph(tmp_path: Path, paragraph: str) -> list[Finding]:
    write_config(tmp_path)
    write(
        tmp_path,
        "docs/rfcs/spans.md",
        "---\nid: spans\ntitle: Spans\nstatus: draft\ndescribes: []\nrfc_state: draft\n"
        "affects: []\nweight: small\n---\n\n# Spans\n\n## Summary\n\n"
        f"{paragraph}\n\n## Decisions\n\nNone.\n\n## Design detail\n\nNames.\n",
    )
    return _findings(tmp_path)


def test_spans_are_counted_by_the_reader_code_references_uses(tmp_path: Path) -> None:
    """A span that itself holds a backtick is one span, so this paragraph holds three."""
    assert _summary_paragraph(tmp_path, "Names ``a`b``, `c` and `d`.") == []
    assert _codes(_summary_paragraph(tmp_path, "Names ``a`b``, `c`, `d` and `e`.")) == [
        "rfc-structure/dense-paragraph"
    ]


def test_spans_in_a_comment_or_a_fence_are_not_a_paragraphs_spans(tmp_path: Path) -> None:
    body = "Says it.\n\n```\n`a` `b` `c` `d` `e`\n```\n\n<!-- `a` `b` `c` `d` `e` -->"

    assert _summary_paragraph(tmp_path, body) == []


def test_text_above_the_first_section_is_the_owners_part(tmp_path: Path) -> None:
    write_config(tmp_path)
    write(
        tmp_path,
        "docs/rfcs/lead.md",
        "---\nid: lead\ntitle: Lead\nstatus: draft\ndescribes: []\nrfc_state: draft\n"
        "affects: []\nweight: small\n---\n\n# Lead\n\nSee `a`, `b`, `c` and `d`.\n\n"
        "## Summary\n\nSays it.\n\n## Decisions\n\nNone.\n\n## Design detail\n\nNames.\n",
    )

    assert _codes(_findings(tmp_path)) == ["rfc-structure/dense-paragraph"]


def test_a_non_rfc_doc_is_ignored(repo: Path) -> None:
    assert by_doc(_findings(repo), "overview") == []
    assert by_doc(_findings(repo), "pick") == []


def test_a_draft_rfc_is_warned_for_what_it_lacks_and_errored_for_misplacing(repo: Path) -> None:
    findings = {
        (finding["doc_id"], finding["code"]): finding
        for finding in check_findings(repo, "--only", "rfc-structure")
    }

    assert findings[("no-weight", "rfc-structure/missing-weight")]["severity"] == "warning"
    assert findings[("cost-moved-down", "rfc-structure/section-out-of-order")]["severity"] == (
        "error"
    )
    assert findings[("empty-decisions", "rfc-structure/missing-section")]["severity"] == "error"
    assert findings[("dense-owner", "rfc-structure/dense-paragraph")]["effective_class"] == "hint"


def test_an_ignore_comment_answers_a_dense_paragraph(tmp_path: Path) -> None:
    paragraph = (
        '<!-- irminsul:ignore rfc-structure/dense-paragraph reason="the names are the point" -->\n'
        "Names `a`, `b`, `c` and `d`."
    )
    _summary_paragraph(tmp_path, paragraph)

    findings = check_findings(tmp_path, "--only", "rfc-structure")

    assert [f for f in findings if f["check"] == "rfc-structure"] == []
