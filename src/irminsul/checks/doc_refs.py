"""DocRefsCheck — every `depends_on` entry must name a doc that exists.

`depends_on` is the strong-dependency edge of the DocGraph: orphan detection,
`refs`, and the context query all walk it. A dangling id never errors anywhere
else — the edge simply fails to materialize and those signals silently weaken.
So this check reports each dangling id as certain, at the offending frontmatter
entry.

Scope is deliberately narrow to avoid overlapping neighbouring checks:
whether a superseded doc is deprecated belongs to `supersession`,
and `resolved_by` and `implements` to `rfc-lifecycle`.
Whether a declared dependency matches a real import relationship is
`import-deps`' business; existence of the referenced doc is the only
invariant enforced here.
"""

from __future__ import annotations

from typing import ClassVar

from irminsul.checks.base import Finding, FindingClass, Severity
from irminsul.docgraph import DocGraph, DocNode
from irminsul.frontmatter import entry_line

CODE_UNKNOWN_DEPENDENCY = "doc-refs/unknown-dependency"


class DocRefsCheck:
    name: ClassVar[str] = "doc-refs"
    default_severity: ClassVar[Severity] = Severity.warning
    explanations: ClassVar[dict[str, str]] = {
        CODE_UNKNOWN_DEPENDENCY: (
            "A `depends_on` entry names a doc id that does not exist in the graph. Fix "
            "the id or remove the entry; run `irminsul refs <id>` to locate the intended "
            "doc."
        ),
    }
    classes: ClassVar[dict[str, FindingClass]] = {
        CODE_UNKNOWN_DEPENDENCY: FindingClass.certain,
    }

    def run(self, graph: DocGraph) -> list[Finding]:
        out: list[Finding] = []
        for node in graph.nodes.values():
            for dep_id in node.frontmatter.depends_on:
                if dep_id in graph.nodes:
                    continue
                out.append(
                    Finding(
                        check=self.name,
                        code=CODE_UNKNOWN_DEPENDENCY,
                        severity=Severity.error,
                        message=(f"'depends_on' references unknown doc id '{dep_id}'"),
                        path=node.path,
                        doc_id=node.id,
                        line=_depends_on_line(graph, node, dep_id),
                        suggestion=(
                            f"remove the entry or fix the id; run `irminsul refs {dep_id}` "
                            "to locate the intended doc"
                        ),
                    )
                )
        return out


def _depends_on_line(graph: DocGraph, node: DocNode, dep_id: str) -> int | None:
    """Line of the dangling entry inside the frontmatter block, when cheaply
    recoverable from disk. None when the graph has no repo root (hand-built
    graphs in tests) or the file can't be read."""
    if graph.repo_root is None:
        return None
    return entry_line(graph.repo_root / node.path, "depends_on", dep_id)
