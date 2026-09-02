"""Lifecycle drift and immutable implemented-RFC enforcement (RFC 0035)."""

from __future__ import annotations

from typing import ClassVar

from irminsul.checks.base import Finding, Fix, Severity
from irminsul.docgraph import DocGraph, DocNode
from irminsul.frontmatter import RfcStateEnum, StatusEnum, canonical_rfc_state
from irminsul.rfc_freeze import compute_frozen_hash, seal_text

CODE_PRE_LIFECYCLE_RFC = "rfc-lifecycle-integrity/pre-lifecycle-rfc"
CODE_MISSING_FROZEN_HASH = "rfc-lifecycle-integrity/missing-frozen-hash"
CODE_FROZEN_CONTENT_CHANGED = "rfc-lifecycle-integrity/frozen-content-changed"
CODE_PREMATURE_FROZEN_HASH = "rfc-lifecycle-integrity/premature-frozen-hash"
CODE_IMPLEMENTATION_EVIDENCE_BEFORE_FINALIZATION = (
    "rfc-lifecycle-integrity/implementation-evidence-before-finalization"
)
CODE_STABLE_DOC_LINKS_DRAFT_RFC = "rfc-lifecycle-integrity/stable-doc-links-draft-rfc"


class RfcLifecycleIntegrityCheck:
    name: ClassVar[str] = "rfc-lifecycle-integrity"
    default_severity: ClassVar[Severity] = Severity.error
    explanations: ClassVar[dict[str, str]] = {
        CODE_PRE_LIFECYCLE_RFC: (
            "An RFC under 80-evolution/rfcs/ has no structured `rfc_state`. Run "
            "`irminsul change migrate <id>` to inspect and classify it."
        ),
        CODE_MISSING_FROZEN_HASH: (
            "An implemented RFC has no `frozen_hash` content seal. Run `irminsul fix "
            "--check rfc-lifecycle-integrity --confirm`."
        ),
        CODE_FROZEN_CONTENT_CHANGED: (
            "An implemented RFC's content changed after it was frozen. Restore the "
            "frozen record and propose the extension in a new RFC."
        ),
        CODE_PREMATURE_FROZEN_HASH: (
            "A non-implemented RFC carries a `frozen_hash` seal reserved for "
            "implemented RFCs. Remove `frozen_hash`, or finalize the RFC through the "
            "lifecycle."
        ),
        CODE_IMPLEMENTATION_EVIDENCE_BEFORE_FINALIZATION: (
            "A doc declares `implements:` an RFC that is not yet implemented. Finalize "
            "the accepted RFC, or remove the premature implementation evidence."
        ),
        CODE_STABLE_DOC_LINKS_DRAFT_RFC: (
            "A stable, live doc links to a still-draft RFC. Verify the behavior is "
            "shipped and finalize the RFC, or stop presenting it as live."
        ),
    }

    def run(self, graph: DocGraph) -> list[Finding]:
        rfc_nodes = _rfc_nodes(graph)
        out: list[Finding] = []
        for node in rfc_nodes.values():
            state = node.frontmatter.rfc_state
            if state is None:
                out.append(
                    _finding(
                        node,
                        "pre-lifecycle-rfc",
                        Severity.warning,
                        "RFC has no structured lifecycle state",
                        f"run `irminsul change migrate {node.id}` to inspect and classify it",
                        data={"problem": "pre-lifecycle-rfc", "rfc": node.id},
                    )
                )
                continue
            canonical = canonical_rfc_state(state)
            frozen_hash = node.frontmatter.frozen_hash
            if canonical == RfcStateEnum.implemented:
                if frozen_hash is None:
                    out.append(
                        _finding(
                            node,
                            "missing-frozen-hash",
                            Severity.warning,
                            "implemented RFC has no frozen content seal",
                            "run `irminsul fix --check rfc-lifecycle-integrity --confirm`",
                        )
                    )
                elif graph.repo_root is not None:
                    text = (graph.repo_root / node.path).read_text(encoding="utf-8")
                    actual = compute_frozen_hash(text)
                    if frozen_hash != actual:
                        out.append(
                            _finding(
                                node,
                                "frozen-content-changed",
                                Severity.error,
                                "implemented RFC changed after it was frozen",
                                "restore the frozen record and propose the extension in a new RFC",
                                data={
                                    "problem": "frozen-content-changed",
                                    "expected": frozen_hash,
                                    "actual": actual,
                                },
                            )
                        )
            elif frozen_hash is not None:
                out.append(
                    _finding(
                        node,
                        "premature-frozen-hash",
                        Severity.error,
                        f"{canonical.value} RFC carries a seal reserved for implemented RFCs",
                        "remove `frozen_hash` or finalize the accepted RFC through the lifecycle",
                    )
                )

        for source in graph.nodes.values():
            for rfc_id in source.frontmatter.implements:
                implemented_rfc = rfc_nodes.get(rfc_id)
                if implemented_rfc is None or implemented_rfc.frontmatter.rfc_state is None:
                    continue
                state = canonical_rfc_state(implemented_rfc.frontmatter.rfc_state)
                if state != RfcStateEnum.implemented:
                    out.append(
                        Finding(
                            check=self.name,
                            code=CODE_IMPLEMENTATION_EVIDENCE_BEFORE_FINALIZATION,
                            category="implementation-evidence-before-finalization",
                            severity=Severity.error,
                            message=(
                                f"doc declares `implements: {rfc_id}` while that RFC is {state.value}"
                            ),
                            path=source.path,
                            doc_id=source.id,
                            suggestion=(
                                "finalize the accepted RFC, or remove the premature implementation evidence"
                            ),
                            data={
                                "problem": "implementation-evidence-before-finalization",
                                "rfc": rfc_id,
                                "state": state.value,
                            },
                        )
                    )

        for rfc_id, target in rfc_nodes.items():
            state = target.frontmatter.rfc_state
            if state is None or canonical_rfc_state(state) != RfcStateEnum.draft:
                continue
            for source_id in graph.inbound_weak.get(rfc_id, set()):
                source_node = graph.nodes.get(source_id)
                if source_node is None or not _is_stable_live_doc(source_node):
                    continue
                out.append(
                    Finding(
                        check=self.name,
                        code=CODE_STABLE_DOC_LINKS_DRAFT_RFC,
                        category="stable-doc-links-draft-rfc",
                        severity=Severity.warning,
                        message=f"stable live documentation links draft RFC '{rfc_id}'",
                        path=source_node.path,
                        doc_id=source_node.id,
                        suggestion=(
                            "verify the behavior is shipped and finalize the RFC, or stop presenting it as live"
                        ),
                        data={
                            "problem": "stable-doc-links-draft-rfc",
                            "rfc": rfc_id,
                        },
                    )
                )
        return out

    def fixes(self, findings: list[Finding], graph: DocGraph) -> list[Fix]:
        return [
            Fix(
                path=finding.path,
                description=f"freeze implemented RFC {finding.doc_id}",
                apply=seal_text,
                requires_confirm=True,
            )
            for finding in findings
            if finding.category == "missing-frozen-hash" and finding.path is not None
        ]


def _rfc_nodes(graph: DocGraph) -> dict[str, DocNode]:
    docs_root = (
        (graph.config.paths.docs_root or "docs").replace("\\", "/").strip("/") or "docs"
        if graph.config
        else "docs"
    )
    prefix = f"{docs_root}/80-evolution/rfcs/"
    return {
        node.id: node
        for node in graph.nodes.values()
        if node.path.as_posix().startswith(prefix) and node.path.name != "INDEX.md"
    }


def _is_stable_live_doc(node: DocNode) -> bool:
    path = f"/{node.path.as_posix()}/"
    return node.frontmatter.status == StatusEnum.stable and not any(
        segment in path for segment in ("/50-decisions/", "/80-evolution/", "/90-meta/")
    )


def _finding(
    node: DocNode,
    category: str,
    severity: Severity,
    message: str,
    suggestion: str,
    *,
    data: dict[str, str] | None = None,
) -> Finding:
    return Finding(
        check=RfcLifecycleIntegrityCheck.name,
        code=f"{RfcLifecycleIntegrityCheck.name}/{category}",
        category=category,
        severity=severity,
        message=message,
        path=node.path,
        doc_id=node.id,
        suggestion=suggestion,
        data=data or {"problem": category},
    )
