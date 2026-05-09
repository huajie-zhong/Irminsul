"""CoverageCheck — every tier-3 doc must declare at least one valid test path."""

from __future__ import annotations

from pathlib import Path
from typing import ClassVar

from irminsul.checks.base import Finding, Severity
from irminsul.docgraph import DocGraph


class CoverageCheck:
    name: ClassVar[str] = "coverage"
    default_severity: ClassVar[Severity] = Severity.error

    def run(self, graph: DocGraph) -> list[Finding]:
        out: list[Finding] = []
        repo_root = graph.repo_root

        for node in graph.nodes.values():
            if node.frontmatter.tier != 3:
                continue

            # Placeholder docs with no describes: claim are not yet covering any
            # source, so requiring tests would be noise. Skip them.
            if not node.frontmatter.describes:
                continue

            if not node.frontmatter.tests:
                out.append(
                    Finding(
                        check=self.name,
                        severity=self.default_severity,
                        message="tier-3 doc has no 'tests:' entries in frontmatter",
                        path=node.path,
                        doc_id=node.id,
                        suggestion="Add `tests: [path/to/test_file.py]` to frontmatter",
                    )
                )
                continue

            if repo_root is None:
                continue

            for test_path in node.frontmatter.tests:
                resolved = repo_root / Path(test_path)
                if not resolved.exists():
                    out.append(
                        Finding(
                            check=self.name,
                            severity=self.default_severity,
                            message=f"tests: entry '{test_path}' does not exist",
                            path=node.path,
                            doc_id=node.id,
                            suggestion=f"Create '{test_path}' or update the tests: field",
                        )
                    )

        return out
