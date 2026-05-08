"""OrphansCheck — docs that nothing links to or claims as a child.

Strong (`depends_on`), weak (markdown body links), and structural (parent
INDEX's `children`) inbound references all count. INDEX.md docs are exempt
because they're navigation; ADRs are exempt because they're append-only and
routinely orphaned (linked from PRs and future ADRs, not always from existing
docs).
"""

from __future__ import annotations

from typing import ClassVar

from irminsul.checks.base import Finding, Severity
from irminsul.docgraph import DocGraph
from irminsul.frontmatter import AudienceEnum


class OrphansCheck:
    name: ClassVar[str] = "orphans"
    default_severity: ClassVar[Severity] = Severity.warning

    def run(self, graph: DocGraph) -> list[Finding]:
        # Collect ids referenced by any INDEX.md's `children`.
        children_set: set[str] = set()
        for node in graph.nodes.values():
            if node.path.name == "INDEX.md":
                children_set.update(node.frontmatter.children)

        out: list[Finding] = []
        for node in graph.nodes.values():
            if node.path.name == "INDEX.md":
                continue
            if node.frontmatter.audience == AudienceEnum.adr:
                continue

            inbound: set[str] = set()
            inbound |= graph.inbound_strong.get(node.id, set())
            inbound |= graph.inbound_weak.get(node.id, set())
            if node.id in children_set:
                continue
            if inbound:
                continue

            out.append(
                Finding(
                    check=self.name,
                    severity=Severity.warning,
                    message=f"orphan: no doc links to or claims '{node.id}'",
                    path=node.path,
                    doc_id=node.id,
                    suggestion=(
                        "add a link from a parent doc, list this id under an "
                        "INDEX.md's 'children', or remove the doc"
                    ),
                )
            )

        return out
