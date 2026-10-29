"""LinksCheck — internal markdown link integrity.

Reads each doc's links from `DocNode.links` and verifies every relative link target
resolves to an existing file inside the repo. Also validates anchor fragments:
same-doc (`#heading`) anchors must match a heading in this doc, cross-doc
anchors (`path.md#heading`) must match a heading in the target doc. External
URLs (`http`/`https`/`mailto`/`tel`) are skipped; that's `ExternalLinksCheck`.
"""

from __future__ import annotations

from pathlib import Path
from typing import ClassVar

from irminsul.checks.base import Finding, FindingClass, Severity
from irminsul.docgraph import DocGraph
from irminsul.docgraph_index import (
    headings_of,
    is_external,
    parse_markdown,
    resolve_href,
)

CODE_BROKEN_LINK = "links/broken-link"
CODE_UNKNOWN_ANCHOR = "links/unknown-anchor"

_STAYS_INSIDE = (
    "a relative link stays inside its own repository: link a file in another repository by "
    "its full URL, which `external-links` checks, or name its path in a code span"
)


def _broken_link(
    path: Path, doc_id: str | None, line: int, href: str, resolved: Path | None
) -> Finding:
    """The finding for a link whose target is missing, or that left the repository."""
    if resolved is None:
        message, data = f"broken link: '{href}' (leaves the repository)", {"target": href}
    else:
        message = f"broken link: '{href}' (resolved to '{resolved.as_posix()}')"
        data = {"target": href, "resolved": resolved.as_posix()}
    return Finding(
        check=LinksCheck.name,
        code=CODE_BROKEN_LINK,
        severity=Severity.error,
        message=message,
        path=path,
        doc_id=doc_id,
        line=line,
        suggestion=_STAYS_INSIDE if resolved is None else None,
        data=data,
    )


class LinksCheck:
    name: ClassVar[str] = "links"
    default_severity: ClassVar[Severity] = Severity.error
    explanations: ClassVar[dict[str, str]] = {
        CODE_BROKEN_LINK: (
            "A relative markdown link does not resolve to an existing file in the repo, or "
            "climbs above the root of the repository its file lives in. Fix the link target "
            "or remove the link. A relative link stays inside its own repository: to point at a "
            "file in another repository, link it by its full URL, which `external-links` "
            "checks, or name its path in a code span."
        ),
        CODE_UNKNOWN_ANCHOR: (
            "A `#heading` link fragment has no matching heading in the target doc "
            "(same-doc or cross-doc), by the slug GitHub gives a heading: `## Scope & Limitations` is "
            "`#scope--limitations`, and a second `## Notes` is `#notes-1`. Fix the fragment or "
            "the heading it points at."
        ),
    }
    classes: ClassVar[dict[str, FindingClass]] = {
        CODE_BROKEN_LINK: FindingClass.certain,
        CODE_UNKNOWN_ANCHOR: FindingClass.certain,
    }

    def run(self, graph: DocGraph) -> list[Finding]:
        if graph.repo_root is None:
            return []

        out: list[Finding] = []

        for node in graph.nodes.values():
            for link in node.links:
                if is_external(link.href):
                    continue

                line = node.file_line(link.line)

                # Same-doc anchor: validate against this doc's headings.
                if not link.target:
                    if link.anchor is None:
                        continue
                    headings = graph.headings.get(node.id, [])
                    if not any(h.anchor == link.anchor for h in headings):
                        out.append(
                            Finding(
                                check=self.name,
                                code=CODE_UNKNOWN_ANCHOR,
                                severity=Severity.error,
                                message=(
                                    f"unknown anchor: '#{link.anchor}' has no matching "
                                    "heading in this doc"
                                ),
                                path=node.path,
                                doc_id=node.id,
                                line=line,
                                data={"anchor": link.anchor},
                            )
                        )
                    continue

                target_rel = resolve_href(node.path.as_posix(), link.target)
                if target_rel is None or not (graph.repo_root / target_rel).exists():
                    out.append(_broken_link(node.path, node.id, line, link.href, target_rel))
                    continue

                # Cross-doc anchor: validate against the target's headings when an
                # anchor was given.
                if link.anchor is None:
                    continue
                target_anchors = self._anchors(graph, target_rel)
                if target_anchors is None:
                    # Not markdown (a source file): anchor validation is undefined.
                    continue
                if link.anchor not in target_anchors:
                    out.append(
                        Finding(
                            check=self.name,
                            code=CODE_UNKNOWN_ANCHOR,
                            severity=Severity.error,
                            message=(
                                f"unknown anchor in '{target_rel}': "
                                f"'#{link.anchor}' has no matching heading"
                            ),
                            path=node.path,
                            doc_id=node.id,
                            line=line,
                            data={
                                "anchor": link.anchor,
                                "target": target_rel.as_posix(),
                            },
                        )
                    )

        out.extend(self._guidance_file_findings(graph))
        return out

    def _anchors(self, graph: DocGraph, rel: Path) -> set[str] | None:
        """Heading anchors of a markdown file, from the graph when it is a doc or guidance file."""
        node = graph.by_path.get(rel)
        if node is not None:
            return {h.anchor for h in graph.headings.get(node.id, [])}
        if rel.suffix.lower() != ".md" or graph.repo_root is None:
            return None
        display = rel.as_posix()
        guidance = next((g for g in graph.guidance_files if g.display == display), None)
        if guidance is not None and guidance.text is not None:
            return {h.anchor for h in guidance.headings}
        try:
            text = (graph.repo_root / rel).read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            return None
        return {h.anchor for h in headings_of(parse_markdown(text))}

    def _guidance_file_findings(self, graph: DocGraph) -> list[Finding]:
        """Broken local links and anchors in guidance files outside the doc graph.

        A link that starts with `/` is not judged.
        """
        assert graph.repo_root is not None
        out: list[Finding] = []
        for guidance in graph.guidance_files:
            for link in guidance.links:
                if is_external(link.href) or link.target.startswith("/"):
                    continue
                resolved = (
                    resolve_href(guidance.display, link.target, guidance.root)
                    if link.target
                    else Path(guidance.display)
                )
                if resolved is not None and link.anchor is not None:
                    anchors = self._anchors(graph, resolved)
                    if anchors is not None and link.anchor not in anchors:
                        out.append(
                            Finding(
                                check=self.name,
                                code=CODE_UNKNOWN_ANCHOR,
                                severity=Severity.error,
                                message=(
                                    f"unknown anchor in '{resolved.as_posix()}': "
                                    f"'#{link.anchor}' has no matching heading"
                                ),
                                path=Path(guidance.display),
                                line=link.line,
                                data={
                                    "anchor": link.anchor,
                                    "target": resolved.as_posix(),
                                },
                            )
                        )
                if not link.target:
                    continue
                if resolved is None or not (graph.repo_root / resolved).exists():
                    out.append(
                        _broken_link(Path(guidance.display), None, link.line, link.href, resolved)
                    )
        return out
