"""FrontmatterCheck — required fields, enums, ID/filename agreement."""

from __future__ import annotations

from typing import ClassVar

from irminsul.checks.base import Finding, Severity
from irminsul.docgraph import DocGraph
from irminsul.frontmatter import expected_id_for


class FrontmatterCheck:
    name: ClassVar[str] = "frontmatter"
    default_severity: ClassVar[Severity] = Severity.error

    def run(self, graph: DocGraph) -> list[Finding]:
        out: list[Finding] = []

        for failure in graph.parse_failures:
            out.append(
                Finding(
                    check=self.name,
                    severity=Severity.error,
                    message=f"frontmatter parse error: {failure.error}",
                    path=failure.path,
                )
            )

        for path in graph.missing_frontmatter:
            out.append(
                Finding(
                    check=self.name,
                    severity=Severity.error,
                    message="missing frontmatter (required for every doc atom)",
                    path=path,
                )
            )

        for node in graph.nodes.values():
            expected = expected_id_for(node.path)
            if node.frontmatter.id != expected:
                out.append(
                    Finding(
                        check=self.name,
                        severity=Severity.error,
                        message=(
                            f"id '{node.frontmatter.id}' does not match filename "
                            f"(expected '{expected}')"
                        ),
                        path=node.path,
                        doc_id=node.frontmatter.id,
                    )
                )

        for dup_id, first_path, conflicting_path in graph.duplicate_ids:
            out.append(
                Finding(
                    check=self.name,
                    severity=Severity.error,
                    message=(f"duplicate id '{dup_id}' (also defined at {first_path})"),
                    path=conflicting_path,
                    doc_id=dup_id,
                )
            )

        return out
