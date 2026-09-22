"""Tests for DuplicateBlockCheck and SectionReferenceCheck."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

import pytest

from irminsul.checks.base import Finding
from irminsul.checks.duplicate_block import DuplicateBlockCheck
from irminsul.checks.section_reference import SectionReferenceCheck
from irminsul.config import find_config, load
from irminsul.docgraph import build_graph


@pytest.fixture
def repo(fixture_repo: Callable[[str], Path]) -> Path:
    return fixture_repo("soft-doc-structure")


def _lines_flagged(repo: Path, findings: list[Finding], rel: str) -> list[str]:
    text = (repo / rel).read_text(encoding="utf-8").splitlines()
    return [text[f.line - 1] for f in findings if f.path and f.path.as_posix() == rel and f.line]


def test_repeated_list_item_is_reported_at_second_occurrence(repo: Path) -> None:
    graph = build_graph(repo, load(find_config(repo)))
    findings = DuplicateBlockCheck().run(graph)

    assert len(findings) == 1
    assert findings[0].code == "duplicate-block/repeated-block"
    assert findings[0].line == 11
    assert "line 9" in findings[0].message


def test_short_repeats_and_fenced_copies_are_ignored(repo: Path) -> None:
    graph = build_graph(repo, load(find_config(repo)))
    findings = DuplicateBlockCheck().run(graph)
    assert not [f for f in findings if f.line != 11]


def test_section_references_report_only_missing_targets(repo: Path) -> None:
    graph = build_graph(repo, load(find_config(repo)))
    findings = SectionReferenceCheck().run(graph)
    flagged = _lines_flagged(repo, findings, "docs/components/references.md")

    assert flagged == [
        "The fields follow Appendix B of the [atom reference](target.md).",
        "See the storage model above.",
        "status: stable   # see status list below",
        "Our own layout is in Appendix Z of this document.",
    ]
    assert {f.code for f in findings} == {
        "section-reference/missing-appendix",
        "section-reference/missing-target",
    }


def test_an_appendix_of_another_document_is_left_alone(repo: Path) -> None:
    """`Appendix B of RFC 9110` is a true sentence about somebody else's document. We
    cannot read their headings, so measuring it against ours reported a fact as a lie."""
    graph = build_graph(repo, load(find_config(repo)))
    findings = SectionReferenceCheck().run(graph)
    flagged = _lines_flagged(repo, findings, "docs/components/references.md")

    assert "The grammar is in Appendix B of RFC 9110." not in flagged
    assert not [line for line in flagged if "rfc-editor.org" in line]
    # Nor the form no keyword list would have caught: the external name is not adjacent.
    assert "Appendix Y, see RFC 9110 for the grammar." not in flagged
    # A reference that says it means this document still fires when the section is absent.
    assert "Our own layout is in Appendix Z of this document." in flagged


def test_a_block_copied_into_another_live_doc_is_reported_once(tmp_path: Path) -> None:
    (tmp_path / "irminsul.toml").write_text(
        'project_name = "r"\n[paths]\ndocs_root = "docs"\nsource_roots = []\n', encoding="utf-8"
    )
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
    graph = build_graph(tmp_path, load(tmp_path / "irminsul.toml"))
    findings = DuplicateBlockCheck().run(graph)
    assert [(f.code, f.path.as_posix()) for f in findings] == [
        ("duplicate-block/copied-block", "docs/guides/b.md")
    ]
    assert findings[0].data["first"] == "docs/guides/a.md:9"


def test_a_paragraph_repeated_under_another_heading_is_reported(tmp_path: Path) -> None:
    """A heading ends a block; it does not scope the comparison. Two sections restating
    one paragraph are exactly the pair that drifts apart, so narrowing this check to
    within-a-section would drop the case it is most useful for."""
    (tmp_path / "irminsul.toml").write_text(
        'project_name = "r"\n[paths]\ndocs_root = "docs"\nsource_roots = []\n', encoding="utf-8"
    )
    shared = "Source discovery walks every configured root and skips paths the ignore list names."
    doc = tmp_path / "docs" / "guides" / "a.md"
    doc.parent.mkdir(parents=True, exist_ok=True)
    doc.write_text(
        f"---\nid: a\ntitle: T\nstatus: stable\n---\n\n# T\n\n## Walking\n\n{shared}\n\n"
        f"## Ignoring\n\n{shared}\n",
        encoding="utf-8",
    )

    findings = DuplicateBlockCheck().run(build_graph(tmp_path, load(tmp_path / "irminsul.toml")))

    assert [f.code for f in findings] == ["duplicate-block/repeated-block"]
    assert findings[0].line == 15
