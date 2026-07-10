"""DocRefsCheck — every `depends_on` entry must name a doc that exists.

`depends_on` is the strong-dependency edge of the DocGraph: orphan detection,
env-var propagation, and the context query all walk it. A dangling id never
errors anywhere else — the edge simply fails to materialize and those signals
silently weaken. This check makes the breakage visible: one warning per
dangling id, pointing at the offending frontmatter entry.

Scope is deliberately narrow to avoid overlapping neighbouring checks:
`supersedes`/`superseded_by` reciprocity belongs to `supersession`,
`resolved_by` to `rfc-resolution`, and `implements` to `decision-updates`.
Whether a declared dependency matches a real import relationship is
`import-deps`' business; existence of the referenced doc is the only
invariant enforced here.
"""

from __future__ import annotations

import re
from typing import ClassVar

from irminsul.checks.base import Finding, Severity
from irminsul.docgraph import DocGraph, DocNode


class DocRefsCheck:
    name: ClassVar[str] = "doc-refs"
    default_severity: ClassVar[Severity] = Severity.warning

    def run(self, graph: DocGraph) -> list[Finding]:
        out: list[Finding] = []
        for node in graph.nodes.values():
            for dep_id in node.frontmatter.depends_on:
                if dep_id in graph.nodes:
                    continue
                out.append(
                    Finding(
                        check=self.name,
                        severity=self.default_severity,
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
    try:
        lines = (graph.repo_root / node.path).read_text(encoding="utf-8").splitlines()
    except OSError:
        return None

    in_list = False
    for index, line in enumerate(lines, start=1):
        stripped = line.strip()
        if stripped == "---" and index > 1:
            break
        if stripped.startswith("depends_on:"):
            in_list = True
            if _mentions(stripped, dep_id):
                return index
            continue
        if not in_list:
            continue
        if stripped.startswith("- ") and _mentions(stripped[2:], dep_id):
            return index
        if stripped and not line.startswith((" ", "\t", "-")):
            in_list = False
    return None


def _mentions(text: str, value: str) -> bool:
    cleaned = text.strip().strip("'\"")
    if cleaned == value:
        return True
    return value in re.split(r"[^A-Za-z0-9_-]+", text)
