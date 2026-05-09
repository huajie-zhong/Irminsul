"""BoundaryCheck — tier-3 docs must declare what the component does NOT do."""

from __future__ import annotations

from typing import ClassVar

from irminsul.checks.base import Finding, Severity
from irminsul.docgraph import DocGraph

_REQUIRED_HEADING = "scope & limitations"


class BoundaryCheck:
    name: ClassVar[str] = "boundary"
    default_severity: ClassVar[Severity] = Severity.warning

    def run(self, graph: DocGraph) -> list[Finding]:
        out: list[Finding] = []
        for node in graph.nodes.values():
            if node.frontmatter.tier != 3:
                continue
            headings = graph.headings.get(node.id, [])
            if not any(_REQUIRED_HEADING in h.text.lower() for h in headings):
                out.append(
                    Finding(
                        check=self.name,
                        severity=self.default_severity,
                        message="tier-3 doc is missing '## Scope & Limitations' section",
                        path=node.path,
                        doc_id=node.id,
                        suggestion="Add a '## Scope & Limitations' section describing what this component does NOT do",
                    )
                )
        return out
