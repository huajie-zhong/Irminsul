"""ChangeBindingCheck — declared change intent vs. derived footprint (RFC 0029).

Two layers, both deterministic:

- **Shape** (always): an accepted or implemented RFC must declare `affects`
  explicitly (`[]` means "intentionally no owned source"), and every declared
  component id must resolve to a doc in the graph.
- **Binding** (only when `check` was given a diff range): compare the union of
  accepted RFCs' declared components with the components that own the changed
  source. Divergence is a review clue, not proof of error — a valid
  implementation may legitimately differ from its initial plan — so
  declared-but-untouched is info and touched-but-undeclared is a warning.
  Changed source with no owning doc at all is delegated to coverage/uniqueness.
"""

from __future__ import annotations

from typing import ClassVar

from irminsul.checks.base import Finding, Severity
from irminsul.config import docs_root_prefix
from irminsul.docgraph import DocGraph, DocNode
from irminsul.frontmatter import RfcStateEnum, canonical_rfc_state

CODE_MISSING_AFFECTS = "change-binding/missing-affects"
CODE_UNKNOWN_COMPONENT = "change-binding/unknown-component"
CODE_TOUCHED_BUT_UNDECLARED = "change-binding/touched-but-undeclared"
CODE_DECLARED_BUT_UNTOUCHED = "change-binding/declared-but-untouched"


class ChangeBindingCheck:
    name: ClassVar[str] = "change-binding"
    default_severity: ClassVar[Severity] = Severity.warning
    explanations: ClassVar[dict[str, str]] = {
        CODE_MISSING_AFFECTS: (
            "An accepted or implemented RFC does not declare `affects`. Declare the "
            "component ids it changes, or `affects: []` for no owned source."
        ),
        CODE_UNKNOWN_COMPONENT: (
            "An `affects` entry does not match any doc id in the graph. Correct the component id."
        ),
        CODE_TOUCHED_BUT_UNDECLARED: (
            "The diff touches a component's owned source, but no accepted RFC declares "
            "it in `affects`. Add the component to the RFC's `affects`, or record why "
            "the change is out of scope."
        ),
        CODE_DECLARED_BUT_UNTOUCHED: (
            "An accepted RFC declares a component in `affects` but the diff contains no "
            "owned source change for it. Implementation may not have started yet; "
            "reconcile `affects` before finalization."
        ),
    }

    def run(self, graph: DocGraph) -> list[Finding]:
        if graph.config is None or graph.repo_root is None:
            return []

        rfc_prefix = f"{docs_root_prefix(graph.config)}/80-evolution/rfcs/"

        rfcs = [
            node
            for node in graph.nodes.values()
            if node.path.as_posix().startswith(rfc_prefix)
            and node.frontmatter.rfc_state is not None
        ]

        out: list[Finding] = []
        for node in rfcs:
            out.extend(self._check_shape(graph, node))

        if graph.diff_changed_paths is not None:
            out.extend(self._check_binding(graph, rfcs))

        return out

    def _check_shape(self, graph: DocGraph, node: DocNode) -> list[Finding]:
        out: list[Finding] = []
        fm = node.frontmatter
        assert fm.rfc_state is not None
        canonical = canonical_rfc_state(fm.rfc_state)

        if canonical in (RfcStateEnum.accepted, RfcStateEnum.implemented) and fm.affects is None:
            out.append(
                Finding(
                    check=self.name,
                    code=CODE_MISSING_AFFECTS,
                    category="missing-affects",
                    severity=Severity.warning,
                    message=(
                        f"{canonical.value} RFC does not declare `affects`; "
                        "declare the component ids it changes, or `affects: []` "
                        "for no owned source"
                    ),
                    path=node.path,
                    doc_id=node.id,
                    suggestion="add `affects:` to the RFC frontmatter",
                )
            )

        for declared in fm.affects or []:
            if declared not in graph.nodes:
                out.append(
                    Finding(
                        check=self.name,
                        code=CODE_UNKNOWN_COMPONENT,
                        category="unknown-component",
                        severity=Severity.warning,
                        message=(
                            f"`affects` entry '{declared}' does not match any doc id in the graph"
                        ),
                        path=node.path,
                        doc_id=node.id,
                        suggestion="correct the component id in `affects`",
                    )
                )

        return out

    def _check_binding(self, graph: DocGraph, rfcs: list[DocNode]) -> list[Finding]:
        from irminsul.change.footprint import touched_components

        assert graph.config is not None and graph.diff_changed_paths is not None

        accepted = [
            node
            for node in rfcs
            if node.frontmatter.rfc_state is not None
            and canonical_rfc_state(node.frontmatter.rfc_state) == RfcStateEnum.accepted
            and node.frontmatter.affects is not None
        ]
        if not accepted:
            return []

        footprint = touched_components(graph, graph.config, graph.diff_changed_paths)
        declared_union = {
            component for node in accepted for component in node.frontmatter.affects or []
        }

        out: list[Finding] = []
        for component in sorted(set(footprint.touched) - declared_union):
            owner = graph.nodes.get(component)
            files = ", ".join(footprint.touched[component])
            out.append(
                Finding(
                    check=self.name,
                    code=CODE_TOUCHED_BUT_UNDECLARED,
                    category="touched-but-undeclared",
                    severity=Severity.warning,
                    message=(
                        f"component '{component}' has changed source ({files}) but no "
                        "accepted RFC declares it in `affects`"
                    ),
                    path=owner.path if owner else None,
                    doc_id=component if owner else None,
                    suggestion=(
                        "add the component to the accepted RFC's `affects` or record "
                        "why the change is out of scope"
                    ),
                )
            )

        for node in accepted:
            untouched = sorted(set(node.frontmatter.affects or []) - set(footprint.touched))
            for component in untouched:
                out.append(
                    Finding(
                        check=self.name,
                        code=CODE_DECLARED_BUT_UNTOUCHED,
                        category="declared-but-untouched",
                        severity=Severity.info,
                        message=(
                            f"accepted RFC declares component '{component}' but the diff "
                            "contains no owned source change for it"
                        ),
                        path=node.path,
                        doc_id=node.id,
                        suggestion=(
                            "implementation may not have started; reconcile `affects` "
                            "before finalization"
                        ),
                    )
                )

        return out
