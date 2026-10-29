"""ChangeBindingCheck — an accepted or implemented RFC declares its scope.

The shape of `affects`, judged on the tree alone: an accepted or implemented RFC must
declare it explicitly (`[]` means "intentionally no owned source"), and every declared
component id must resolve to a doc in the graph.

Whether a change stays inside what an RFC declares is not judged here. `check --diff` cannot
know which RFC a change is for, and the union of every accepted RFC's `affects` is not that
RFC, so `change verify` and `change finalize` compare the change with the one RFC they are
given.
"""

from __future__ import annotations

from typing import ClassVar

from irminsul.checks.base import Finding, FindingClass, Severity, certain_severity
from irminsul.docgraph import DocGraph, DocNode, is_rfc

CODE_MISSING_AFFECTS = "change-binding/missing-affects"
CODE_UNKNOWN_COMPONENT = "change-binding/unknown-component"


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
    }
    classes: ClassVar[dict[str, FindingClass]] = {
        CODE_MISSING_AFFECTS: FindingClass.certain,
        CODE_UNKNOWN_COMPONENT: FindingClass.certain,
    }

    def run(self, graph: DocGraph) -> list[Finding]:
        if graph.config is None or graph.repo_root is None:
            return []

        out: list[Finding] = []
        for node in graph.nodes.values():
            if is_rfc(node, graph.config) and node.frontmatter.rfc_state is not None:
                out.extend(self._check_shape(graph, node))
        return out

    def _check_shape(self, graph: DocGraph, node: DocNode) -> list[Finding]:
        from irminsul.change.gate import missing_affects, unknown_components

        assert node.frontmatter.rfc_state is not None
        missing = missing_affects(node, node.frontmatter.rfc_state)
        found = [(missing, Severity.error)] if missing else []
        found += [(issue, certain_severity(node)) for issue in unknown_components(graph, node)]
        return [
            Finding(
                check=self.name,
                code=issue.code,
                severity=severity,
                message=issue.message,
                path=node.path,
                doc_id=node.id,
                suggestion=issue.suggestion,
            )
            for issue, severity in found
        ]
