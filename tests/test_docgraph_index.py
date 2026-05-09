"""Tests for the lazy index builders on `DocGraph`."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from markdown_it import MarkdownIt

from irminsul.config import find_config, load
from irminsul.docgraph import build_graph
from irminsul.docgraph_index import (
    build_headings,
    build_inbound_strong,
    build_inbound_weak,
    slugify,
)


def test_slugify_basic() -> None:
    assert slugify("Hello World") == "hello-world"
    assert slugify("  Extra   Spaces  ") == "extra-spaces"
    assert slugify("Multi-Hyphen-Heading") == "multi-hyphen-heading"
    assert slugify("Heading With (Parens)?") == "heading-with-parens"


def test_inbound_strong_from_depends_on(fixture_repo: Callable[[str], Path]) -> None:
    repo = fixture_repo("good")
    config = load(find_config(repo))
    graph = build_graph(repo, config)
    # The "good" fixture has just one node; its inbound_strong should be empty
    # but the dict should be populated for it.
    assert "composer" in graph.inbound_strong
    assert graph.inbound_strong["composer"] == set()


def test_inbound_weak_from_body_link(fixture_repo: Callable[[str], Path]) -> None:
    repo = fixture_repo("soft-orphans")
    config = load(find_config(repo))
    graph = build_graph(repo, config)
    # overview.md links to ../20-components/hub.md → inbound_weak[hub] contains overview.
    assert "overview" in graph.inbound_weak["hub"]


def test_headings_extracted(fixture_repo: Callable[[str], Path]) -> None:
    repo = fixture_repo("soft-orphans")
    config = load(find_config(repo))
    graph = build_graph(repo, config)
    overview_headings = graph.headings["overview"]
    slugs = {h.slug for h in overview_headings}
    assert "overview" in slugs


def test_build_inbound_strong_isolated() -> None:
    # Build a tiny graph by hand to exercise the pure builder.

    from irminsul.docgraph import DocNode
    from irminsul.frontmatter import AudienceEnum, DocFrontmatter, StatusEnum

    def _node(node_id: str, depends_on: list[str]) -> DocNode:
        fm = DocFrontmatter(
            id=node_id,
            title=node_id,
            audience=AudienceEnum.explanation,
            tier=3,
            status=StatusEnum.stable,
            depends_on=depends_on,
        )
        return DocNode(id=node_id, path=Path(f"{node_id}.md"), frontmatter=fm, body="")

    nodes = {
        "a": _node("a", []),
        "b": _node("b", ["a"]),
        "c": _node("c", ["a", "b"]),
    }
    inbound = build_inbound_strong(nodes)
    assert inbound["a"] == {"b", "c"}
    assert inbound["b"] == {"c"}
    assert inbound["c"] == set()


def test_build_inbound_weak_skips_externals() -> None:
    from irminsul.docgraph import DocNode
    from irminsul.frontmatter import AudienceEnum, DocFrontmatter, StatusEnum

    fm_kwargs = {
        "audience": AudienceEnum.explanation,
        "tier": 3,
        "status": StatusEnum.stable,
    }
    a = DocNode(
        id="a",
        path=Path("docs/a.md"),
        frontmatter=DocFrontmatter(id="a", title="A", **fm_kwargs),
        body="See [external](https://example.com) and [b](b.md).",
    )
    b = DocNode(
        id="b",
        path=Path("docs/b.md"),
        frontmatter=DocFrontmatter(id="b", title="B", **fm_kwargs),
        body="",
    )
    nodes = {"a": a, "b": b}
    by_path = {Path("docs/a.md"): a, Path("docs/b.md"): b}

    md = MarkdownIt("commonmark")
    inbound = build_inbound_weak(nodes, by_path, md)
    assert inbound["b"] == {"a"}
    assert inbound["a"] == set()


def test_build_headings_records_levels_and_lines() -> None:
    from irminsul.docgraph import DocNode
    from irminsul.frontmatter import AudienceEnum, DocFrontmatter, StatusEnum

    fm = DocFrontmatter(
        id="x",
        title="X",
        audience=AudienceEnum.explanation,
        tier=3,
        status=StatusEnum.stable,
    )
    body = "# Top\n\nintro\n\n## Sub\n\ncontent\n"
    node = DocNode(id="x", path=Path("x.md"), frontmatter=fm, body=body)

    md = MarkdownIt("commonmark")
    headings = build_headings({"x": node}, md)
    assert [h.text for h in headings["x"]] == ["Top", "Sub"]
    assert [h.level for h in headings["x"]] == [1, 2]
    assert [h.slug for h in headings["x"]] == ["top", "sub"]
