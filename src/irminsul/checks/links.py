"""LinksCheck — internal markdown link integrity.

Walks each doc body via markdown-it and verifies every relative link target
resolves to an existing file inside the repo. Also validates anchor fragments:
same-doc (`#heading`) anchors must match a heading in this doc, cross-doc
anchors (`path.md#heading`) must match a heading in the target doc. External
URLs (`http`/`https`/`mailto`/`tel`) are skipped; that's `ExternalLinksCheck`.
"""

from __future__ import annotations

from pathlib import Path, PurePosixPath
from typing import ClassVar
from urllib.parse import urlparse

from markdown_it import MarkdownIt

from irminsul.checks.base import Finding, Severity
from irminsul.docgraph import DocGraph, DocNode

_SKIP_SCHEMES = {"http", "https", "mailto", "tel", "ftp", "ftps", "data"}


def is_external(href: str) -> bool:
    """Return True for absolute URLs we don't validate (http, mailto, etc.)."""
    if not href:
        return True
    parsed = urlparse(href)
    return parsed.scheme.lower() in _SKIP_SCHEMES


def extract_link_hrefs(body: str, md: MarkdownIt) -> list[str]:
    """Return every href attribute on a link_open token in the doc body."""
    hrefs: list[str] = []
    tokens = md.parse(body)
    for token in tokens:
        if token.type == "inline" and token.children:
            for child in token.children:
                if child.type == "link_open":
                    href = child.attrGet("href")
                    if isinstance(href, str):
                        hrefs.append(href)
    return hrefs


# Backwards-compatible alias; the underscore-prefixed name is the original.
_extract_link_hrefs = extract_link_hrefs


def _split_href(href: str) -> tuple[str, str | None]:
    """Return (path_part, anchor) where anchor is None if no '#' present."""
    if "#" not in href:
        return href, None
    path_part, anchor = href.split("#", 1)
    return path_part, anchor or None


def _resolve_target_path(doc: DocNode, target: str) -> Path:
    """Resolve a relative target string to a repo-relative POSIX path."""
    doc_parent = PurePosixPath(doc.path.as_posix()).parent
    raw = doc_parent / target
    parts: list[str] = []
    for part in raw.parts:
        if part == "..":
            if parts:
                parts.pop()
        elif part != ".":
            parts.append(part)
    return Path(*parts)


class LinksCheck:
    name: ClassVar[str] = "links"
    default_severity: ClassVar[Severity] = Severity.error

    def __init__(self) -> None:
        self._md = MarkdownIt("commonmark")

    def run(self, graph: DocGraph) -> list[Finding]:
        if graph.repo_root is None:
            return []

        out: list[Finding] = []

        for node in graph.nodes.values():
            for href in extract_link_hrefs(node.body, self._md):
                if is_external(href):
                    continue

                path_part, anchor = _split_href(href)

                # Same-doc anchor: validate against this doc's headings.
                if not path_part:
                    if anchor is None:
                        continue
                    headings = graph.headings.get(node.id, [])
                    if not any(h.slug == anchor for h in headings):
                        out.append(
                            Finding(
                                check=self.name,
                                severity=Severity.error,
                                message=(
                                    f"unknown anchor: '#{anchor}' has no matching "
                                    "heading in this doc"
                                ),
                                path=node.path,
                                doc_id=node.id,
                            )
                        )
                    continue

                target_rel = _resolve_target_path(node, path_part)
                target_abs = graph.repo_root / target_rel

                if not target_abs.exists():
                    out.append(
                        Finding(
                            check=self.name,
                            severity=Severity.error,
                            message=f"broken link: '{href}' (resolved to '{target_rel}')",
                            path=node.path,
                            doc_id=node.id,
                        )
                    )
                    continue

                # Cross-doc anchor: validate against the target doc's headings,
                # if the target is a known doc node and an anchor was given.
                if anchor is None:
                    continue
                target_node = graph.by_path.get(target_rel)
                if target_node is None:
                    # Target file exists but isn't a doc node (e.g. README, source
                    # file). Anchor validation is undefined; skip silently.
                    continue
                target_headings = graph.headings.get(target_node.id, [])
                if not any(h.slug == anchor for h in target_headings):
                    out.append(
                        Finding(
                            check=self.name,
                            severity=Severity.error,
                            message=(
                                f"unknown anchor in '{target_rel}': "
                                f"'#{anchor}' has no matching heading"
                            ),
                            path=node.path,
                            doc_id=node.id,
                        )
                    )

        return out
