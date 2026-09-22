"""LinksCheck — internal markdown link integrity.

Walks each doc body via markdown-it and verifies every relative link target
resolves to an existing file inside the repo. Also validates anchor fragments:
same-doc (`#heading`) anchors must match a heading in this doc, cross-doc
anchors (`path.md#heading`) must match a heading in the target doc. External
URLs (`http`/`https`/`mailto`/`tel`) are skipped; that's `ExternalLinksCheck`.
"""

from __future__ import annotations

import posixpath
from pathlib import Path, PurePosixPath
from typing import ClassVar
from urllib.parse import unquote, urlparse

from markdown_it import MarkdownIt

from irminsul.checks.base import Finding, FindingClass, Severity
from irminsul.docgraph import DocGraph, DocNode, guidance_files
from irminsul.docgraph_index import slugify

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


def _split_href(href: str) -> tuple[str, str | None]:
    """Return (path_part, anchor) where anchor is None if no '#' present."""
    if "#" not in href:
        return href, None
    path_part, anchor = href.split("#", 1)
    return path_part, anchor or None


def resolve_target_path(doc: DocNode, target: str) -> Path:
    """Resolve a relative target string to a repo-relative POSIX path."""
    doc_parent = PurePosixPath(doc.path.as_posix()).parent
    raw = doc_parent / unquote(target)
    parts: list[str] = []
    for part in raw.parts:
        if part == "..":
            if parts:
                parts.pop()
        elif part != ".":
            parts.append(part)
    return Path(*parts)


CODE_BROKEN_LINK = "links/broken-link"
CODE_UNKNOWN_ANCHOR = "links/unknown-anchor"


class LinksCheck:
    name: ClassVar[str] = "links"
    default_severity: ClassVar[Severity] = Severity.error
    explanations: ClassVar[dict[str, str]] = {
        CODE_BROKEN_LINK: (
            "A relative markdown link does not resolve to an existing file in the repo. "
            "Fix the link target or remove the link."
        ),
        CODE_UNKNOWN_ANCHOR: (
            "A `#heading` link fragment has no matching heading in the target doc "
            "(same-doc or cross-doc). Fix the anchor slug or the heading it points at."
        ),
    }
    classes: ClassVar[dict[str, FindingClass]] = {
        CODE_BROKEN_LINK: FindingClass.certain,
        CODE_UNKNOWN_ANCHOR: FindingClass.certain,
    }

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
                                code=CODE_UNKNOWN_ANCHOR,
                                severity=Severity.error,
                                message=(
                                    f"unknown anchor: '#{anchor}' has no matching "
                                    "heading in this doc"
                                ),
                                path=node.path,
                                doc_id=node.id,
                                data={"problem": "unknown-anchor", "anchor": anchor},
                            )
                        )
                    continue

                target_rel = resolve_target_path(node, path_part)
                target_abs = graph.repo_root / target_rel

                if not target_abs.exists():
                    out.append(
                        Finding(
                            check=self.name,
                            code=CODE_BROKEN_LINK,
                            severity=Severity.error,
                            message=f"broken link: '{href}' (resolved to '{target_rel.as_posix()}')",
                            path=node.path,
                            doc_id=node.id,
                            data={
                                "problem": "broken-link",
                                "target": href,
                                "resolved": target_rel.as_posix(),
                            },
                        )
                    )
                    continue

                # Cross-doc anchor: validate against the target doc's headings,
                # if the target is a known doc node and an anchor was given.
                if anchor is None:
                    continue
                target_slugs = self._slugs(graph, target_rel)
                if target_slugs is None:
                    # Not markdown (a source file): anchor validation is undefined.
                    continue
                if anchor not in target_slugs:
                    out.append(
                        Finding(
                            check=self.name,
                            code=CODE_UNKNOWN_ANCHOR,
                            severity=Severity.error,
                            message=(
                                f"unknown anchor in '{target_rel}': "
                                f"'#{anchor}' has no matching heading"
                            ),
                            path=node.path,
                            doc_id=node.id,
                            data={
                                "problem": "unknown-anchor",
                                "anchor": anchor,
                                "target": target_rel.as_posix(),
                            },
                        )
                    )

        if graph.config is not None:
            out.extend(self._guidance_file_findings(graph))
        return out

    def _slugs(self, graph: DocGraph, rel: Path) -> set[str] | None:
        """Heading slugs of a markdown file, from the graph when it is a doc node."""
        node = graph.by_path.get(rel)
        if node is not None:
            return {h.slug for h in graph.headings.get(node.id, [])}
        if rel.suffix.lower() != ".md" or graph.repo_root is None:
            return None
        try:
            text = (graph.repo_root / rel).read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            return None
        tokens = self._md.parse(text)
        return {
            slugify(tokens[i + 1].content)
            for i, token in enumerate(tokens[:-1])
            if token.type == "heading_open" and tokens[i + 1].type == "inline"
        }

    def _guidance_file_findings(self, graph: DocGraph) -> list[Finding]:
        """Broken local links and anchors in guidance files outside the doc graph."""
        assert graph.repo_root is not None and graph.config is not None
        out: list[Finding] = []
        for display, absolute in guidance_files(graph.repo_root, graph.config):
            try:
                text = absolute.read_text(encoding="utf-8")
            except (OSError, UnicodeDecodeError):
                continue
            for href in extract_link_hrefs(text, self._md):
                path_part, anchor = _split_href(href)
                if is_external(href) or path_part.startswith("/"):
                    continue
                resolved = (
                    posixpath.normpath(posixpath.join(posixpath.dirname(display), path_part))
                    if path_part
                    else display
                )
                if anchor is not None:
                    slugs = self._slugs(graph, Path(resolved))
                    if slugs is not None and anchor not in slugs:
                        out.append(
                            Finding(
                                check=self.name,
                                code=CODE_UNKNOWN_ANCHOR,
                                severity=Severity.error,
                                message=(
                                    f"unknown anchor in '{resolved}': "
                                    f"'#{anchor}' has no matching heading"
                                ),
                                path=Path(display),
                                data={
                                    "problem": "unknown-anchor",
                                    "anchor": anchor,
                                    "target": resolved,
                                },
                            )
                        )
                if not path_part:
                    continue
                if not (graph.repo_root / resolved).exists():
                    out.append(
                        Finding(
                            check=self.name,
                            code=CODE_BROKEN_LINK,
                            severity=Severity.error,
                            message=f"broken link: '{href}' (resolved to '{resolved}')",
                            path=Path(display),
                            data={"problem": "broken-link", "target": href, "resolved": resolved},
                        )
                    )
        return out
