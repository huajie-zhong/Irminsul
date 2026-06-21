"""IndexGraduationCheck — a layer with real content whose INDEX is still draft.

This is the complement of `phantom-layer`. A `status: draft` INDEX means
"layer under construction"; `phantom-layer` tolerates it while the layer is
hollow (downgrading to info). But once the layer has actual content docs, the
draft label is stale — the layer is populated, so its INDEX should graduate to
`stable`. Leaving it draft hides a populated layer from every consumer that
treats `stable` as "ready" (`liar`, `reality`, overlap analysis, …).

Pairs with the seed/scaffold lifecycle: a freshly scaffolded layer starts
hollow + draft (info), and graduates to stable the moment content lands.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import ClassVar

from irminsul.checks.base import Finding, Fix, Severity
from irminsul.docgraph import DocGraph
from irminsul.frontmatter import StatusEnum
from irminsul.frontmatter_edit import set_value


class IndexGraduationCheck:
    name: ClassVar[str] = "index-graduation"
    default_severity: ClassVar[Severity] = Severity.warning

    def run(self, graph: DocGraph) -> list[Finding]:
        index_by_dir = {}
        dirs_with_content: set[str] = set()
        for node in graph.nodes.values():
            parent = node.path.parent.as_posix()
            if node.path.name == "INDEX.md":
                index_by_dir[parent] = node
            else:
                dirs_with_content.add(parent)

        out: list[Finding] = []
        for parent, index_node in index_by_dir.items():
            if index_node.frontmatter.status != StatusEnum.draft:
                continue
            if parent not in dirs_with_content:
                continue  # hollow: that is phantom-layer's business, not ours
            out.append(
                Finding(
                    check=self.name,
                    severity=self.default_severity,
                    message=(
                        f"layer '{parent}' has content but its INDEX is still "
                        "status: draft — graduate it to stable"
                    ),
                    path=index_node.path,
                    doc_id=index_node.id,
                    suggestion="set status: stable in the layer INDEX",
                )
            )
        return out

    def fixes(self, findings: list[Finding], graph: DocGraph) -> list[Fix]:
        """Graduate a populated layer's INDEX to `stable`.

        Touches load-bearing status frontmatter, so it requires `--confirm`.
        Gated on this check's own findings.
        """
        flagged = {
            finding.doc_id
            for finding in findings
            if finding.check == self.name and finding.doc_id is not None
        }
        out: list[Fix] = []
        for node in graph.nodes.values():
            if node.id not in flagged:
                continue
            out.append(
                Fix(
                    path=node.path,
                    description=f"set status: stable in {node.path.as_posix()}",
                    apply=_status_setter(StatusEnum.stable.value),
                    requires_confirm=True,
                )
            )
        return out


def _status_setter(value: str) -> Callable[[str], str]:
    def apply(text: str) -> str:
        return set_value(text, "status", value)

    return apply
