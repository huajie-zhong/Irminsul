"""Lazy indexes layered on top of `DocGraph`.

Three indexes are built once at the end of `build_graph` and used by Sprint 2
checks:

- `inbound_strong` — for each doc id, the set of doc ids whose `depends_on`
  includes it. Used by orphans and supersession reciprocity.
- `inbound_weak` — for each doc id, the set of doc ids whose body contains a
  markdown link resolving to that doc. Used by orphans.
- `headings` — for each doc id, the ordered list of headings in its body. Used
  by anchor validation.

Builders are pure: they take only the inputs they read and return new dicts.
`docgraph.build_graph` calls them; checks consume the populated fields.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path, PurePosixPath

from markdown_it import MarkdownIt

from irminsul.docgraph import DocNode


@dataclass(frozen=True)
class Heading:
    level: int
    text: str
    slug: str
    line: int


_NON_WORD = re.compile(r"[^\w\s-]")
_WHITESPACE = re.compile(r"[\s]+")
_DASHES = re.compile(r"-+")


def slugify(text: str) -> str:
    """A small, dependency-free slug close to GitHub/MkDocs Material output."""
    s = text.strip().lower()
    s = _NON_WORD.sub("", s)
    s = _WHITESPACE.sub("-", s)
    s = _DASHES.sub("-", s)
    return s.strip("-")


def build_inbound_strong(nodes: dict[str, DocNode]) -> dict[str, set[str]]:
    inbound: dict[str, set[str]] = {doc_id: set() for doc_id in nodes}
    for src_id, node in nodes.items():
        for target_id in node.frontmatter.depends_on:
            inbound.setdefault(target_id, set()).add(src_id)
        for target_id in node.frontmatter.implements:
            inbound.setdefault(target_id, set()).add(src_id)
    return inbound


def _resolve_link_to_doc_id(
    src_node: DocNode,
    href: str,
    by_path: dict[Path, DocNode],
) -> str | None:
    """If `href` is a relative path that resolves to a known doc, return that
    doc's id. Otherwise None (external URL, anchor-only, or non-doc target)."""
    if not href or href.startswith("#"):
        return None
    if "://" in href or href.startswith(("mailto:", "tel:")):
        return None

    target = href.split("#", 1)[0]
    if not target:
        return None

    doc_parent = PurePosixPath(src_node.path.as_posix()).parent
    raw = doc_parent / target
    parts: list[str] = []
    for part in raw.parts:
        if part == "..":
            if parts:
                parts.pop()
        elif part != ".":
            parts.append(part)
    resolved = Path(*parts)
    return by_path[resolved].id if resolved in by_path else None


def build_inbound_weak(
    nodes: dict[str, DocNode],
    by_path: dict[Path, DocNode],
    md: MarkdownIt,
) -> dict[str, set[str]]:
    inbound: dict[str, set[str]] = {doc_id: set() for doc_id in nodes}
    for src_id, node in nodes.items():
        tokens = md.parse(node.body)
        for token in tokens:
            if token.type != "inline" or not token.children:
                continue
            for child in token.children:
                if child.type != "link_open":
                    continue
                href = child.attrGet("href")
                if not isinstance(href, str):
                    continue
                target_id = _resolve_link_to_doc_id(node, href, by_path)
                if target_id is None or target_id == src_id:
                    continue
                inbound.setdefault(target_id, set()).add(src_id)
    return inbound


def build_headings(
    nodes: dict[str, DocNode],
    md: MarkdownIt,
) -> dict[str, list[Heading]]:
    headings: dict[str, list[Heading]] = {}
    for doc_id, node in nodes.items():
        h_list: list[Heading] = []
        tokens = md.parse(node.body)
        i = 0
        while i < len(tokens):
            token = tokens[i]
            if token.type == "heading_open":
                level = int(token.tag[1:]) if token.tag.startswith("h") else 0
                line = (token.map[0] + 1) if token.map else 0
                # The next inline token holds the heading text.
                if i + 1 < len(tokens) and tokens[i + 1].type == "inline":
                    text = tokens[i + 1].content
                    h_list.append(Heading(level=level, text=text, slug=slugify(text), line=line))
            i += 1
        headings[doc_id] = h_list
    return headings
