"""Tests for the section reader `adr-structure` and `rfc-structure` share."""

from __future__ import annotations

from pathlib import Path

from irminsul.checks.sections import RequiredSection, section_gaps

from .conftest import load_graph, write_config, write_doc

_REQUIRED = (
    RequiredSection("summary", "Summary", substantive=True),
    RequiredSection("problem", "Problem"),
)


def _gaps(tmp_path: Path, body: str) -> list[tuple[str, str, int | None]]:
    repo = tmp_path / "r"
    write_config(repo)
    write_doc(repo, "docs/rfcs/pick.md", doc_id="pick", body=body)
    graph = load_graph(repo)
    node = graph.nodes["pick"]
    return [
        (gap.section.slug, gap.kind, gap.line)
        for gap in section_gaps(node, graph.headings["pick"], _REQUIRED)
    ]


def test_each_required_section_present_once_has_no_gap(tmp_path: Path) -> None:
    assert _gaps(tmp_path, "## Summary\n\nSays it.\n\n## Problem\n") == []


def test_an_absent_section_is_missing(tmp_path: Path) -> None:
    assert _gaps(tmp_path, "## Summary\n\nSays it.\n") == [("problem", "missing", None)]


def test_a_repeated_section_is_a_duplicate_at_its_second_heading(tmp_path: Path) -> None:
    gaps = _gaps(tmp_path, "## Summary\n\nSays it.\n\n## Problem\n\n## Problem\n")

    assert [(slug, kind) for slug, kind, _ in gaps] == [("problem", "duplicate")]
    assert gaps[0][2] is not None


def test_only_a_substantive_section_must_say_something(tmp_path: Path) -> None:
    body = "## Summary\n\n<!-- the gain -->\n\n## Problem\n\n<!-- the example -->\n"
    gaps = _gaps(tmp_path, body)

    assert [(slug, kind) for slug, kind, _ in gaps] == [("summary", "empty")]
    assert gaps[0][2] is not None


def test_a_marked_placeholder_is_not_substance(tmp_path: Path) -> None:
    body = "## Summary\n\nWhat changes. <!-- irminsul:placeholder -->\n\n## Problem\n"

    assert [(slug, kind) for slug, kind, _ in _gaps(tmp_path, body)] == [("summary", "empty")]


def test_a_heading_in_a_fence_is_not_a_section(tmp_path: Path) -> None:
    body = "```\n## Summary\n```\n\n## Problem\n"

    assert [(slug, kind) for slug, kind, _ in _gaps(tmp_path, body)] == [("summary", "missing")]
