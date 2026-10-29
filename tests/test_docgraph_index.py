"""Tests for the lazy index builders on `DocGraph`."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

import pytest

from irminsul.docgraph_index import (
    build_headings,
    build_inbound_strong,
    build_inbound_weak,
    headings_of,
    links_of,
    parse_markdown,
    resolve_href,
    section_lines,
    slugify,
    split_href,
)

from .conftest import load_graph, write, write_config


def test_slugify_basic() -> None:
    assert slugify("Hello World") == "hello-world"
    assert slugify("  Extra Spaces  ") == "extra-spaces"
    assert slugify("Multi-Hyphen-Heading") == "multi-hyphen-heading"
    assert slugify("Heading With (Parens)?") == "heading-with-parens"


def test_slugify_follows_github_for_punctuation_and_unicode() -> None:
    assert slugify("Scope & Limitations") == "scope--limitations"
    assert slugify("Extra   Spaces") == "extra---spaces"
    assert slugify("Run - then stop") == "run---then-stop"
    assert slugify("snake_case Name") == "snake_case-name"
    assert slugify("Café Menu") == "café-menu"
    assert slugify("& First") == "-first"


def test_a_repeated_heading_is_anchored_with_a_numeric_suffix() -> None:
    body = "# Doc\n\n## Notes\n\n## Notes\n\n## Notes-1\n\n## Notes\n"

    headings = headings_of(parse_markdown(body))

    assert [(h.slug, h.anchor) for h in headings] == [
        ("doc", "doc"),
        ("notes", "notes"),
        ("notes", "notes-1"),
        ("notes-1", "notes-1-1"),
        ("notes", "notes-2"),
    ]


def test_a_heading_is_slugged_from_its_rendered_text() -> None:
    body = "## See [the guide](other.md), `code` and _more_ &amp; **bold**\n"

    [heading] = headings_of(parse_markdown(body))

    assert heading.slug == "see-the-guide-code-and-more--bold"


def test_inbound_strong_from_depends_on(fixture_repo: Callable[[str], Path]) -> None:
    repo = fixture_repo("good")
    graph = load_graph(repo)
    # The "good" fixture has just one node; its inbound_strong should be empty
    # but the dict should be populated for it.
    assert "composer" in graph.inbound_strong
    assert graph.inbound_strong["composer"] == set()


def test_inbound_weak_from_body_link(fixture_repo: Callable[[str], Path]) -> None:
    repo = fixture_repo("soft-orphans")
    graph = load_graph(repo)
    # overview.md links to ../components/hub.md → inbound_weak[hub] contains overview.
    assert "overview" in graph.inbound_weak["hub"]


def test_headings_extracted(fixture_repo: Callable[[str], Path]) -> None:
    repo = fixture_repo("soft-orphans")
    graph = load_graph(repo)
    overview_headings = graph.headings["overview"]
    slugs = {h.slug for h in overview_headings}
    assert "overview" in slugs


def test_build_inbound_strong_isolated() -> None:
    # Build a tiny graph by hand to exercise the pure builder.

    from irminsul.docgraph import DocNode
    from irminsul.frontmatter import DocFrontmatter, StatusEnum

    def _node(node_id: str, depends_on: list[str]) -> DocNode:
        fm = DocFrontmatter(
            id=node_id,
            title=node_id,
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


def test_build_inbound_strong_includes_implements_and_resolved_by() -> None:
    from irminsul.docgraph import DocNode
    from irminsul.frontmatter import DocFrontmatter, RfcStateEnum, StatusEnum

    fm_kwargs = {
        "status": StatusEnum.stable,
    }
    rfc = DocNode(
        id="rfc-1",
        path=Path("docs/rfcs/rfc-1.md"),
        frontmatter=DocFrontmatter(
            id="rfc-1",
            title="RFC",
            rfc_state=RfcStateEnum.accepted,
            resolved_by="docs/decisions/adr-1.md",
            required_updates=[],
            **fm_kwargs,
        ),
        body="",
    )
    adr = DocNode(
        id="adr-1",
        path=Path("docs/decisions/adr-1.md"),
        frontmatter=DocFrontmatter(
            id="adr-1",
            title="ADR",
            status=StatusEnum.stable,
        ),
        body="",
    )
    component = DocNode(
        id="component",
        path=Path("docs/components/component.md"),
        frontmatter=DocFrontmatter(
            id="component",
            title="Component",
            implements=["rfc-1"],
            **fm_kwargs,
        ),
        body="",
    )

    inbound = build_inbound_strong({"rfc-1": rfc, "adr-1": adr, "component": component})
    assert inbound["rfc-1"] == {"component"}
    assert inbound["adr-1"] == {"rfc-1"}


def test_build_inbound_weak_skips_externals() -> None:
    from irminsul.docgraph import DocNode
    from irminsul.frontmatter import DocFrontmatter, StatusEnum

    fm_kwargs = {
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

    inbound = build_inbound_weak(nodes, by_path)
    assert inbound["b"] == {"a"}
    assert inbound["a"] == set()


def test_build_headings_records_levels_and_lines() -> None:
    from irminsul.docgraph import DocNode
    from irminsul.frontmatter import DocFrontmatter, StatusEnum

    fm = DocFrontmatter(
        id="x",
        title="X",
        status=StatusEnum.stable,
    )
    body = "# Top\n\nintro\n\n## Sub\n\ncontent\n"
    node = DocNode(id="x", path=Path("x.md"), frontmatter=fm, body=body)

    headings = build_headings({"x": node})
    assert [h.text for h in headings["x"]] == ["Top", "Sub"]
    assert [h.level for h in headings["x"]] == [1, 2]
    assert [h.slug for h in headings["x"]] == ["top", "sub"]


def test_links_of_reads_an_anchor_tags_href_and_its_line() -> None:
    body = (
        "Plain [md](a.md#x) then <a href='b.md'>b</a>,\n"
        'and <a\nclass="c" href="c.md?q=1&amp;r=2#top">c</a> <abbr href="no.md">z</abbr>\n'
        '<a name="anchor"></a> <A HREF=d.md>d</A>\n'
    )

    links = links_of(parse_markdown(body))

    assert [(link.href, link.line, link.target, link.anchor) for link in links] == [
        ("a.md#x", 1, "a.md", "x"),
        ("b.md", 1, "b.md", None),
        ("c.md?q=1&r=2#top", 3, "c.md?q=1&r=2", "top"),
        ("d.md", 4, "d.md", None),
    ]


def test_split_href_reads_an_empty_fragment_as_none() -> None:
    assert split_href("x.md#") == ("x.md", None)
    assert split_href("#") == ("", None)
    assert split_href("x.md#top#more") == ("x.md", "top#more")
    assert split_href("x.md") == ("x.md", None)


@pytest.mark.parametrize(
    ("source", "target", "root", "expected"),
    [
        ("docs/a.md", "b.md", "", "docs/b.md"),
        ("docs/a.md", "../README.md", "", "README.md"),
        ("docs/a.md", "./sub/../b.md", "", "docs/b.md"),
        ("docs/a.md", "my%20notes.md", "", "docs/my notes.md"),
        ("docs/a.md", "/docs/b.md", "", "docs/b.md"),
        ("docs/a.md", "../../x.md", "", None),
        ("a.md", "../x.md", "", None),
        ("a.md", "..x/y.md", "", "..x/y.md"),
        ("../code/README.md", "src/cli.py", "../code", "../code/src/cli.py"),
        ("../code/README.md", "/src/cli.py", "../code", "../code/src/cli.py"),
        ("../code/README.md", "../docs/x.md", "../code", None),
        ("../code/README.md", "../docs/x.md", None, "../docs/x.md"),
        ("../code/README.md", "../../code/src/cli.py", "../code", None),
    ],
)
def test_resolve_href_follows_githubs_rules(
    source: str, target: str, root: str | None, expected: str | None
) -> None:
    resolved = resolve_href(source, target, root)

    assert (None if resolved is None else resolved.as_posix()) == expected


def test_headings_of_reads_levels_and_lines_in_order() -> None:
    body = "# Top\n\n```\n# not a heading\n```\n\n## Sub\n\n<!--\n## nor this\n-->\n\nSetext\n---\n"

    assert [(h.level, h.text, h.line) for h in headings_of(parse_markdown(body))] == [
        (1, "Top", 1),
        (2, "Sub", 7),
        (2, "Setext", 13),
    ]


def test_section_lines_run_to_the_next_heading_of_the_same_or_higher_level() -> None:
    body = (
        "# Doc\n\n## Scope\n\nKept.\n\n```\n# in a fence\n```\n\n### Deeper\n\nAlso kept.\n\n"
        "<!--\n## in a comment\n-->\n\n## Next\n\nNot kept.\n"
    )
    headings = headings_of(parse_markdown(body))

    section = section_lines(body, headings, lambda heading: heading.slug == "scope")

    assert section is not None
    assert "Kept." in section and "# in a fence" in section and "Also kept." in section
    assert "## in a comment" in section
    assert "Not kept." not in section
    assert section_lines(body, headings, lambda heading: heading.slug == "absent") is None
    assert section_lines(body, headings, lambda heading: heading.slug == "next") == [
        "",
        "Not kept.",
    ]


def test_a_link_in_an_anchor_tag_makes_a_weak_backlink(tmp_path: Path) -> None:
    write_config(tmp_path)
    for doc_id, body in (("a", 'See <a href="b.md">b</a>.'), ("b", "Nothing.")):
        write(
            tmp_path,
            f"docs/{doc_id}.md",
            f"---\nid: {doc_id}\ntitle: {doc_id}\nstatus: stable\n---\n\n{body}\n",
        )

    graph = load_graph(tmp_path)

    assert graph.inbound_weak["b"] == {"a"}
