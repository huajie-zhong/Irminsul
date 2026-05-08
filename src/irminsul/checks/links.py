"""LinksCheck — internal markdown link integrity.

Walks each doc body via markdown-it and verifies every relative link target
resolves to an existing file inside the repo. External URLs (`http`/`https`/
`mailto`/`tel`) and same-doc anchor links (`#heading`) are skipped — same-doc
anchor validation and external link checking land in Sprint 2.
"""

from __future__ import annotations

from pathlib import PurePosixPath
from typing import ClassVar
from urllib.parse import urlparse

from markdown_it import MarkdownIt

from irminsul.checks.base import Finding, Severity
from irminsul.docgraph import DocGraph, DocNode

_SKIP_SCHEMES = {"http", "https", "mailto", "tel", "ftp", "ftps", "data"}


def _is_external_or_anchor(href: str) -> bool:
    if not href:
        return True
    if href.startswith("#"):
        return True
    parsed = urlparse(href)
    return parsed.scheme.lower() in _SKIP_SCHEMES


def _extract_link_hrefs(body: str, md: MarkdownIt) -> list[str]:
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


def _resolve_target(doc: DocNode, href: str, repo_root: PurePosixPath) -> PurePosixPath:
    """Resolve a relative link's target to a repo-relative POSIX path.

    Strips the trailing `#anchor`, treats the href as relative to the doc's
    parent directory, and joins onto `repo_root` to canonicalize.
    """
    target = href.split("#", 1)[0]
    doc_parent = PurePosixPath(doc.path.as_posix()).parent
    # Posix-normalize by going through parts; PurePosixPath handles "../".
    raw = doc_parent / target
    # PurePosixPath has no resolve(); collapse .. manually.
    parts: list[str] = []
    for part in raw.parts:
        if part == "..":
            if parts:
                parts.pop()
        elif part != ".":
            parts.append(part)
    return PurePosixPath(*parts)


class LinksCheck:
    name: ClassVar[str] = "links"
    default_severity: ClassVar[Severity] = Severity.error

    def __init__(self) -> None:
        self._md = MarkdownIt("commonmark")

    def run(self, graph: DocGraph) -> list[Finding]:
        if graph.repo_root is None:
            return []

        repo_root_posix = PurePosixPath(*graph.repo_root.resolve().parts)
        out: list[Finding] = []

        for node in graph.nodes.values():
            for href in _extract_link_hrefs(node.body, self._md):
                if _is_external_or_anchor(href):
                    continue

                target_rel = _resolve_target(node, href, repo_root_posix)
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

        return out
