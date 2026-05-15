"""DecisionFollowupsCheck — decision follow-through invariants (RFC-0018).

Surfaces unfinished decision work: accepted RFCs that have not declared or
completed their follow-up docs, follow-up docs that haven't linked back to
the driving decision, broken `implements` references, and planned claims
whose cited RFC has already been resolved.
"""

from __future__ import annotations

import re
from pathlib import Path, PurePosixPath
from typing import ClassVar

from irminsul.checks.base import Finding, Severity
from irminsul.docgraph import DocGraph, DocNode
from irminsul.frontmatter import ClaimStateEnum, RfcStateEnum

_RESOLVED_STATES = frozenset({RfcStateEnum.accepted, RfcStateEnum.rejected, RfcStateEnum.withdrawn})
_RFC_PATH_RE = re.compile(r"80-evolution/rfcs/[^/]+\.md$")


class DecisionFollowupsCheck:
    name: ClassVar[str] = "decision-followups"
    default_severity: ClassVar[Severity] = Severity.warning

    def run(self, graph: DocGraph) -> list[Finding]:
        out: list[Finding] = []
        docs_root = graph.config.paths.docs_root.strip("/\\") if graph.config else "docs"
        rfc_prefix = f"{docs_root}/80-evolution/rfcs/"

        for node in graph.nodes.values():
            is_rfc = node.path.as_posix().startswith(rfc_prefix)
            if is_rfc and node.frontmatter.rfc_state == RfcStateEnum.accepted:
                out.extend(self._check_accepted_rfc(graph, node))
            out.extend(self._check_implements(graph, node))
            out.extend(self._check_planned_claims(graph, node, rfc_prefix))

        return out

    def _check_accepted_rfc(self, graph: DocGraph, node: DocNode) -> list[Finding]:
        out: list[Finding] = []
        followups = node.frontmatter.followups

        if followups is None:
            out.append(
                Finding(
                    check=self.name,
                    severity=Severity.warning,
                    message=(
                        "accepted RFC has no `followups` field; "
                        "add `followups: []` if no docs need updating"
                    ),
                    path=node.path,
                    doc_id=node.id,
                    suggestion="add `followups: []` or list docs that must be created/updated",
                )
            )
            return out

        for entry in followups:
            target_path = Path(PurePosixPath(entry.path))
            target = graph.by_path.get(target_path)

            if target is None:
                out.append(
                    Finding(
                        check=self.name,
                        severity=Severity.warning,
                        message=(
                            f"follow-up path '{entry.path}' listed on accepted RFC "
                            f"does not exist in the graph"
                        ),
                        path=node.path,
                        doc_id=node.id,
                        suggestion="create the doc or correct the path in `followups`",
                    )
                )
            else:
                back_linkers = graph.inbound_strong.get(node.id, set())
                if target.id not in back_linkers:
                    out.append(
                        Finding(
                            check=self.name,
                            severity=Severity.warning,
                            message=(
                                f"follow-up doc '{target.path.as_posix()}' does not "
                                f"link back to RFC '{node.id}' via `implements`"
                            ),
                            path=target.path,
                            doc_id=target.id,
                            suggestion=(
                                f'add `implements: ["{node.id}"]` to {target.path.as_posix()}'
                            ),
                        )
                    )

        return out

    def _check_implements(self, graph: DocGraph, node: DocNode) -> list[Finding]:
        out: list[Finding] = []
        for impl_id in node.frontmatter.implements:
            if impl_id not in graph.nodes:
                out.append(
                    Finding(
                        check=self.name,
                        severity=Severity.warning,
                        message=(
                            f"`implements` entry '{impl_id}' does not match any doc in the graph"
                        ),
                        path=node.path,
                        doc_id=node.id,
                        suggestion="correct the doc ID in `implements`",
                    )
                )
        return out

    def _check_planned_claims(
        self, graph: DocGraph, node: DocNode, rfc_prefix: str
    ) -> list[Finding]:
        out: list[Finding] = []
        for claim in node.frontmatter.claims:
            if claim.state != ClaimStateEnum.planned:
                continue
            for evidence in claim.evidence:
                if not _RFC_PATH_RE.search(evidence):
                    continue
                rfc_path = Path(PurePosixPath(evidence))
                rfc_node = graph.by_path.get(rfc_path)
                if rfc_node is None:
                    continue
                rfc_state = rfc_node.frontmatter.rfc_state
                if rfc_state in _RESOLVED_STATES:
                    out.append(
                        Finding(
                            check=self.name,
                            severity=Severity.warning,
                            message=(
                                f"planned claim '{claim.id}' cites RFC "
                                f"'{rfc_node.id}' which is now {rfc_state.value}; "
                                f"update the claim state"
                            ),
                            path=node.path,
                            doc_id=node.id,
                            suggestion=(
                                f"change claim '{claim.id}' state from 'planned' "
                                f"to 'implemented' (or 'available' / 'enabled') "
                                f"once the feature is live"
                            ),
                        )
                    )
        return out
