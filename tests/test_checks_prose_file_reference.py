"""Tests for ProseFileReferenceCheck."""

from __future__ import annotations

from pathlib import Path

from irminsul.checks.prose_file_reference import ProseFileReferenceCheck

from .conftest import check_codes, load_graph, write_config, write_doc


def _findings(root: Path, body: str, *, status: str = "stable", rel: str = "components/widget.md"):
    write_config(root, source_roots=["src"])
    write_doc(root, f"docs/{rel}", doc_id="widget", status=status, body=body)
    return ProseFileReferenceCheck().run(load_graph(root))


def test_a_bare_name_in_plain_text_is_flagged(tmp_path: Path) -> None:
    findings = _findings(tmp_path, "See neighbor.md for details.")

    assert len(findings) == 1
    assert findings[0].severity.value == "error"
    assert "neighbor.md" in findings[0].message


def test_a_code_span_is_a_literal_mention(tmp_path: Path) -> None:
    assert _findings(tmp_path, "See `neighbor.md` for details.") == []


def test_a_fenced_block_is_a_literal_mention(tmp_path: Path) -> None:
    body = (
        "```text\nneighbor.md\n```\n\n"
        "~~~\nother.md\n~~~\n\n"
        "````markdown\n```\nthird.md\n```\n````\n"
    )

    assert _findings(tmp_path, body) == []


def test_an_indented_code_block_and_an_html_comment_are_not_prose(tmp_path: Path) -> None:
    body = "Example:\n\n    neighbor.md\n\n<!-- other.md -->\n\nInline <!-- third.md --> here.\n"

    assert _findings(tmp_path, body) == []


def test_a_name_beside_a_code_span_is_still_flagged(tmp_path: Path) -> None:
    findings = _findings(tmp_path, "The `literal.md` span and bare.md beside it.")

    assert [f.message for f in findings] == [
        "local markdown reference 'bare.md' is not a Markdown link"
    ]


def test_each_flagged_line_is_the_line_that_names_the_file(tmp_path: Path) -> None:
    body = (
        "# Heading heading.md\n\n"
        "First line\nsecond line second.md\nthird `code\nspan` line third.md\n\n"
        "- item item.md\n\n> quote quote.md\n\n| table.md | cell |\n"
    )
    findings = _findings(tmp_path, body)

    doc_lines = (tmp_path / "docs/components/widget.md").read_text(encoding="utf-8").splitlines()
    named = {f.message.split("'")[1]: doc_lines[(f.line or 0) - 1] for f in findings}
    assert set(named) == {
        "heading.md",
        "second.md",
        "third.md",
        "item.md",
        "quote.md",
        "table.md",
    }
    assert all(name in line for name, line in named.items())


def test_one_finding_is_reported_per_line(tmp_path: Path) -> None:
    findings = _findings(tmp_path, "See a.md and b.md on one line.\nThen c.md here.")

    assert [f.message.split("'")[1] for f in findings] == ["a.md", "c.md"]


def test_prose_file_reference_reads_a_draft(tmp_path: Path) -> None:
    """A bare file name rots as quietly in a draft as in a stable doc."""
    findings = _findings(tmp_path, "See neighbor.md for details.", status="draft")

    assert [f.code for f in findings] == ["prose-file-reference/unlinked-reference"]


def test_prose_file_reference_skips_a_deprecated_doc(tmp_path: Path) -> None:
    assert _findings(tmp_path, "See neighbor.md for details.", status="deprecated") == []


def test_prose_file_reference_skips_an_rfc(tmp_path: Path) -> None:
    assert _findings(tmp_path, "See neighbor.md for details.", rel="rfcs/widget.md") == []


def test_prose_file_reference_allows_links(tmp_path: Path) -> None:
    assert _findings(tmp_path, "See [neighbor](neighbor.md) and <https://example.org/a.md>.") == []


def test_prose_file_reference_allows_reference_links_definitions_and_images(
    tmp_path: Path,
) -> None:
    body = "See [neighbor][neighbor-doc].\n![diagram](diagram.md)\n\n[neighbor-doc]: neighbor.md"

    assert _findings(tmp_path, body) == []


def test_a_definition_that_cannot_start_there_is_plain_text(tmp_path: Path) -> None:
    """CommonMark does not let a definition interrupt a paragraph, so on the next line of
    one it is text, and the reference link above it is not a link."""
    body = "See [neighbor][neighbor-doc].\n[neighbor-doc]: neighbor.md"

    assert [f.line for f in _findings(tmp_path, body)] == [11]


def test_prose_file_reference_allows_link_text_that_wraps_a_line(tmp_path: Path) -> None:
    """CommonMark lets link text continue across a soft line break, so the target on the
    second line is a link's, not prose."""
    body = (
        "See the [unlisted\n  siblings](neighbor.md) for details, and\n"
        "[read\nother.md](other.md) too.\n"
    )

    assert _findings(tmp_path, body) == []


def test_prose_file_reference_still_flags_a_bare_name_beside_a_wrapped_link(
    tmp_path: Path,
) -> None:
    findings = _findings(tmp_path, "See [unlisted\nsiblings](neighbor.md) and bare.md here.\n")

    assert [f.message for f in findings] == [
        "local markdown reference 'bare.md' is not a Markdown link"
    ]


def test_prose_file_reference_does_not_carry_an_open_bracket_across_a_paragraph(
    tmp_path: Path,
) -> None:
    """A `[` that never closes ends with its paragraph; it does not hide the next one."""
    findings = _findings(tmp_path, "Opened [here and never closed.\n\nSee neighbor.md](x) now.\n")

    assert [f.message for f in findings] == [
        "local markdown reference 'neighbor.md' is not a Markdown link"
    ]


def test_an_ignore_comment_does_not_answer_the_finding(tmp_path: Path) -> None:
    """The finding is certain, so no comment silences it; a leftover marker is reported."""
    write_config(tmp_path, source_roots=["src"], enabled=["prose-file-reference"])
    write_doc(
        tmp_path,
        "docs/components/widget.md",
        doc_id="widget",
        body='See neighbor.md here. <!-- irminsul:ignore prose-file-reference reason="old" -->',
    )

    assert check_codes(tmp_path) == [
        "ignore-comment/certain-finding",
        "ignore-comment/unused",
        "prose-file-reference/unlinked-reference",
    ]
