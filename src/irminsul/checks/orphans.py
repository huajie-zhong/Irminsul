"""OrphansCheck — docs that nothing links to or claims as a sibling.

Strong (`depends_on`), weak (markdown body links), and structural (folder
co-location with an INDEX.md) inbound references all count. INDEX.md docs are
exempt because they're navigation; ADRs are exempt because they're append-only
and routinely orphaned (linked from PRs and future ADRs, not always from
existing docs).
"""

from __future__ import annotations

from pathlib import Path
from typing import ClassVar

from irminsul.checks.base import Finding, Severity
from irminsul.docgraph import DocGraph
from irminsul.frontmatter import AudienceEnum


class OrphansCheck:
    name: ClassVar[str] = "orphans"
    default_severity: ClassVar[Severity] = Severity.warning

    def run(self, graph: DocGraph) -> list[Finding]:
        # Folders that have an INDEX.md auto-own their direct siblings.
        indexed_folders: set[Path] = set()
        for node in graph.nodes.values():
            if node.path.name == "INDEX.md":
                indexed_folders.add(node.path.parent)

        out: list[Finding] = []
        for node in graph.nodes.values():
            if node.path.name == "INDEX.md":
                continue
            if node.frontmatter.audience == AudienceEnum.adr:
                continue

            inbound: set[str] = set()
            inbound |= graph.inbound_strong.get(node.id, set())
            inbound |= graph.inbound_weak.get(node.id, set())
            if node.path.parent in indexed_folders:
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
                        "add a link from a parent doc, put this file in a folder "
                        "that has an INDEX.md, or remove the doc"
                    ),
                )
            )

        return out
