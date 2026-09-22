"""RfcLifecycleCheck — the RFC invariants that block.

Every RFC declares its state, `resolved_by` and `implements` point at real docs, and no
doc claims to implement an RFC that has not been finalized. That an implemented RFC stays
unchanged is enforced against git history by `diff-integrity`.
"""

from __future__ import annotations

from pathlib import Path, PurePosixPath
from typing import ClassVar

from irminsul.checks.base import Finding, FindingClass, Severity
from irminsul.docgraph import DocGraph, DocNode, rfc_nodes
from irminsul.frontmatter import RfcStateEnum

CODE_MISSING_RFC_STATE = "rfc-lifecycle/missing-rfc-state"

CODE_DANGLING_RESOLVED_BY = "rfc-lifecycle/dangling-resolved-by"
CODE_BROKEN_IMPLEMENTS = "rfc-lifecycle/broken-implements"
CODE_IMPLEMENTS_BEFORE_IMPLEMENTED = "rfc-lifecycle/implements-before-implemented"
CODE_IMPLEMENTED_WITHOUT_EVIDENCE = "rfc-lifecycle/implemented-without-evidence"


class RfcLifecycleCheck:
    name: ClassVar[str] = "rfc-lifecycle"
    default_severity: ClassVar[Severity] = Severity.error
    explanations: ClassVar[dict[str, str]] = {
        CODE_MISSING_RFC_STATE: (
            "An RFC has no `rfc_state`. Declare `rfc_state: draft|accepted|implemented|rejected` "
            "in its frontmatter."
        ),
        CODE_DANGLING_RESOLVED_BY: (
            "An accepted or implemented RFC's `resolved_by` names a path with no doc in "
            "the graph. It must be a repo-relative POSIX path to an existing decision doc."
        ),
        CODE_BROKEN_IMPLEMENTS: (
            "An `implements` entry does not match any doc in the graph. Correct the doc id."
        ),
        CODE_IMPLEMENTS_BEFORE_IMPLEMENTED: (
            "A doc declares `implements:` an RFC that is not yet implemented. Finalize "
            "the accepted RFC, or remove the premature implementation evidence."
        ),
        CODE_IMPLEMENTED_WITHOUT_EVIDENCE: (
            "An RFC says it is implemented, but no doc names it in `implements:`, so "
            "nothing in the tree records what implementing it changed. `irminsul change "
            "finalize` writes those back-links; a state edited by hand does not. Finalize "
            "the RFC properly, or return it to `accepted` until it really is done. An RFC "
            "that changes no behaviour says so with a `No new behavioral requirements:` "
            "disposition and is not asked for evidence."
        ),
    }
    classes: ClassVar[dict[str, FindingClass]] = {
        CODE_MISSING_RFC_STATE: FindingClass.certain,
        CODE_DANGLING_RESOLVED_BY: FindingClass.certain,
        CODE_BROKEN_IMPLEMENTS: FindingClass.certain,
        CODE_IMPLEMENTS_BEFORE_IMPLEMENTED: FindingClass.certain,
        CODE_IMPLEMENTED_WITHOUT_EVIDENCE: FindingClass.certain,
    }

    def run(self, graph: DocGraph) -> list[Finding]:
        rfcs = rfc_nodes(graph)
        implemented_ids = {
            rfc_id for node in graph.nodes.values() for rfc_id in node.frontmatter.implements
        }
        out: list[Finding] = []
        for node in rfcs.values():
            out.extend(self._check_rfc(graph, node))
            out.extend(self._check_evidence(graph, node, implemented_ids))
        for source in graph.nodes.values():
            out.extend(self._check_implements(graph, rfcs, source))
        return out

    def _check_rfc(self, graph: DocGraph, node: DocNode) -> list[Finding]:
        state = node.frontmatter.rfc_state
        if state is None:
            return [
                _finding(
                    node,
                    CODE_MISSING_RFC_STATE,
                    "RFC has no `rfc_state`",
                    "declare `rfc_state: draft|accepted|implemented|rejected` in frontmatter",
                )
            ]
        out: list[Finding] = []
        resolved_by = node.frontmatter.resolved_by
        if (
            state in (RfcStateEnum.accepted, RfcStateEnum.implemented)
            and resolved_by is not None
            and graph.by_path.get(Path(PurePosixPath(resolved_by))) is None
        ):
            out.append(
                _finding(
                    node,
                    CODE_DANGLING_RESOLVED_BY,
                    f"resolved_by points to '{resolved_by}' but no such doc was found in the graph",
                    "check the path; resolved_by is a repo-relative POSIX path to an existing "
                    "decision doc",
                )
            )
        return out

    def _check_evidence(
        self, graph: DocGraph, node: DocNode, implemented_ids: set[str]
    ) -> list[Finding]:
        """An implemented RFC that nothing in the tree records implementing.

        `change finalize` writes an `implements:` back-link into every component it
        binds, so a properly finalized RFC always has one. Editing `rfc_state` by hand
        does not — and the fabricated record is then sealed like any other.
        """
        if node.frontmatter.rfc_state != RfcStateEnum.implemented:
            return []
        if node.id in implemented_ids:
            return []
        section = graph.requirements.get(node.id)
        if section is not None and section.disposition:
            return []  # declares it changes no behaviour, so there is nothing to bind
        return [
            _finding(
                node,
                CODE_IMPLEMENTED_WITHOUT_EVIDENCE,
                "RFC is marked implemented but no doc names it in `implements:`",
                "finalize it with `irminsul change finalize`, or return it to `accepted` "
                "until the work is really done",
            )
        ]

    def _check_implements(
        self, graph: DocGraph, rfcs: dict[str, DocNode], source: DocNode
    ) -> list[Finding]:
        out: list[Finding] = []
        for rfc_id in source.frontmatter.implements:
            if rfc_id not in graph.nodes:
                out.append(
                    _finding(
                        source,
                        CODE_BROKEN_IMPLEMENTS,
                        f"`implements` entry '{rfc_id}' does not match any doc in the graph",
                        "correct the doc id in `implements`",
                    )
                )
                continue
            rfc = rfcs.get(rfc_id)
            state = rfc.frontmatter.rfc_state if rfc is not None else None
            if state is not None and state != RfcStateEnum.implemented:
                out.append(
                    _finding(
                        source,
                        CODE_IMPLEMENTS_BEFORE_IMPLEMENTED,
                        f"doc declares `implements: {rfc_id}` while that RFC is {state.value}",
                        "finalize the accepted RFC, or remove the premature implementation "
                        "evidence",
                        data={"rfc": rfc_id, "state": state.value},
                    )
                )
        return out


def _finding(
    node: DocNode,
    code: str,
    message: str,
    suggestion: str,
    *,
    data: dict[str, str] | None = None,
) -> Finding:
    category = code.split("/", 1)[1]
    return Finding(
        check=RfcLifecycleCheck.name,
        code=code,
        category=category,
        severity=Severity.error,
        message=message,
        path=node.path,
        doc_id=node.id,
        suggestion=suggestion,
        data={"problem": category, **(data or {})},
    )
