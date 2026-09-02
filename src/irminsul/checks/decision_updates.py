"""DecisionUpdatesCheck - decision integration invariants (RFC-0018).

Surfaces unfinished decision work: accepted RFCs that have not declared or
completed their required doc updates, required update docs that have not linked
back to the driving decision, broken `implements` references, and planned
claims whose cited RFC has already been resolved.
"""

from __future__ import annotations

import re
from collections.abc import Callable
from pathlib import Path, PurePosixPath
from typing import ClassVar

from irminsul.checks.base import Finding, Fix, Severity
from irminsul.docgraph import DocGraph, DocNode
from irminsul.frontmatter import ClaimStateEnum, RfcStateEnum
from irminsul.frontmatter_edit import add_to_list

_RESOLVED_STATES = frozenset(
    {
        RfcStateEnum.accepted,
        RfcStateEnum.implemented,
        RfcStateEnum.rejected,
        RfcStateEnum.withdrawn,
    }
)
_UPDATE_TRACKED_STATES = frozenset({RfcStateEnum.accepted, RfcStateEnum.implemented})
_RFC_PATH_RE = re.compile(r"80-evolution/rfcs/[^/\s)]+\.md")


def _implements_adder(rfc_id: str) -> Callable[[str], str]:
    def apply(text: str) -> str:
        return add_to_list(text, "implements", rfc_id)

    return apply


def _docs_root_prefix(docs_root: str) -> str:
    normalized = docs_root.replace("\\", "/").strip("/")
    parts = [part for part in normalized.split("/") if part not in ("", ".")]
    return PurePosixPath(*parts).as_posix() if parts else ""


CODE_NO_REQUIRED_UPDATES_FIELD = "decision-updates/no-required-updates-field"
CODE_MISSING_REQUIRED_UPDATE_PATH = "decision-updates/missing-required-update-path"
CODE_MISSING_BACKLINK = "decision-updates/missing-backlink"
CODE_BROKEN_IMPLEMENTS = "decision-updates/broken-implements"
CODE_STALE_CLAIM = "decision-updates/stale-claim"


class DecisionUpdatesCheck:
    name: ClassVar[str] = "decision-updates"
    default_severity: ClassVar[Severity] = Severity.warning
    explanations: ClassVar[dict[str, str]] = {
        CODE_NO_REQUIRED_UPDATES_FIELD: (
            "An accepted or implemented RFC has no `required_updates` field. Add "
            "`required_updates: []` if no downstream docs need updating, or list the "
            "docs that must be created/updated/reviewed."
        ),
        CODE_MISSING_REQUIRED_UPDATE_PATH: (
            "A `required_updates` path listed on the RFC does not exist in the graph. "
            "Create the doc or correct the path."
        ),
        CODE_MISSING_BACKLINK: (
            "A required-update doc does not link back to the driving RFC via "
            '`implements`. Add `implements: ["<rfc-id>"]` to the doc.'
        ),
        CODE_BROKEN_IMPLEMENTS: (
            "An `implements` entry does not match any doc in the graph. Correct the doc id."
        ),
        CODE_STALE_CLAIM: (
            "A `planned` claim cites an RFC that is now accepted, implemented, "
            "rejected, or withdrawn. Update the claim's state to match reality."
        ),
    }

    def run(self, graph: DocGraph) -> list[Finding]:
        out: list[Finding] = []
        docs_root = _docs_root_prefix(graph.config.paths.docs_root if graph.config else "docs")
        rfc_prefix = f"{docs_root}/80-evolution/rfcs/" if docs_root else "80-evolution/rfcs/"

        for node in graph.nodes.values():
            is_rfc = node.path.as_posix().startswith(rfc_prefix)
            if is_rfc and node.frontmatter.rfc_state in _UPDATE_TRACKED_STATES:
                out.extend(self._check_accepted_rfc(graph, node))
            out.extend(self._check_implements(graph, node))
            out.extend(self._check_planned_claims(graph, node, docs_root))

        return out

    def _check_accepted_rfc(self, graph: DocGraph, node: DocNode) -> list[Finding]:
        out: list[Finding] = []
        required_updates = node.frontmatter.required_updates
        state = node.frontmatter.rfc_state
        state_label = state.value if state else "accepted"

        if required_updates is None:
            out.append(
                Finding(
                    check=self.name,
                    code=CODE_NO_REQUIRED_UPDATES_FIELD,
                    category="no-required-updates-field",
                    severity=Severity.warning,
                    message=(
                        f"{state_label} RFC has no `required_updates` field; "
                        "add `required_updates: []` if no downstream docs need updating"
                    ),
                    path=node.path,
                    doc_id=node.id,
                    suggestion=(
                        "add `required_updates: []` or list docs that must be "
                        "created/updated/reviewed"
                    ),
                )
            )
            return out

        for entry in required_updates:
            target_path = Path(PurePosixPath(entry.path))
            target = graph.by_path.get(target_path)

            if target is None:
                out.append(
                    Finding(
                        check=self.name,
                        code=CODE_MISSING_REQUIRED_UPDATE_PATH,
                        category="missing-required-update-path",
                        severity=Severity.warning,
                        message=(
                            f"required update path '{entry.path}' listed on {state_label} "
                            f"RFC does not exist in the graph"
                        ),
                        path=node.path,
                        doc_id=node.id,
                        suggestion="create the doc or correct the path in `required_updates`",
                    )
                )
            elif (
                not self._is_resolved_by_target(node, target)
                and node.id not in target.frontmatter.implements
            ):
                out.append(
                    Finding(
                        check=self.name,
                        code=CODE_MISSING_BACKLINK,
                        category="missing-backlink",
                        severity=Severity.warning,
                        message=(
                            f"required update doc '{target.path.as_posix()}' does not "
                            f"link back to RFC '{node.id}' via `implements`"
                        ),
                        path=target.path,
                        doc_id=target.id,
                        suggestion=(f'add `implements: ["{node.id}"]` to {target.path.as_posix()}'),
                    )
                )

        return out

    def fixes(self, findings: list[Finding], graph: DocGraph) -> list[Fix]:
        """Add the driving RFC's id to a required-update doc's `implements` list.

        Purely additive inverse pointer (RFC 0018), so it applies without
        `--confirm`. Gated on the `missing-backlink` findings already emitted.
        """
        fixable = {
            finding.doc_id
            for finding in findings
            if finding.check == self.name and finding.category == "missing-backlink"
        }
        if not fixable:
            return []

        docs_root = _docs_root_prefix(graph.config.paths.docs_root if graph.config else "docs")
        rfc_prefix = f"{docs_root}/80-evolution/rfcs/" if docs_root else "80-evolution/rfcs/"

        out: list[Fix] = []
        for node in graph.nodes.values():
            is_rfc = node.path.as_posix().startswith(rfc_prefix)
            if not (is_rfc and node.frontmatter.rfc_state in _UPDATE_TRACKED_STATES):
                continue
            for entry in node.frontmatter.required_updates or []:
                target = graph.by_path.get(Path(PurePosixPath(entry.path)))
                if target is None or target.id not in fixable:
                    continue
                if self._is_resolved_by_target(node, target):
                    continue
                if node.id in target.frontmatter.implements:
                    continue
                out.append(
                    Fix(
                        path=target.path,
                        description=f"add implements: {node.id} to {target.path.as_posix()}",
                        apply=_implements_adder(node.id),
                    )
                )
        return out

    def _is_resolved_by_target(self, node: DocNode, target: DocNode) -> bool:
        resolved_by = node.frontmatter.resolved_by
        if resolved_by is None:
            return False
        return target.path == Path(PurePosixPath(resolved_by))

    def _check_implements(self, graph: DocGraph, node: DocNode) -> list[Finding]:
        out: list[Finding] = []
        for impl_id in node.frontmatter.implements:
            if impl_id not in graph.nodes:
                out.append(
                    Finding(
                        check=self.name,
                        code=CODE_BROKEN_IMPLEMENTS,
                        category="broken-implements",
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
        self, graph: DocGraph, node: DocNode, docs_root: str
    ) -> list[Finding]:
        out: list[Finding] = []
        for claim in node.frontmatter.claims:
            if claim.state != ClaimStateEnum.planned:
                continue
            for evidence in claim.evidence:
                match = _RFC_PATH_RE.search(evidence)
                if match is None:
                    continue
                rfc_path = Path(PurePosixPath(docs_root) / match.group(0))
                rfc_node = graph.by_path.get(rfc_path)
                if rfc_node is None:
                    continue
                rfc_state = rfc_node.frontmatter.rfc_state
                if rfc_state in _RESOLVED_STATES:
                    out.append(
                        Finding(
                            check=self.name,
                            code=CODE_STALE_CLAIM,
                            category="stale-claim",
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
