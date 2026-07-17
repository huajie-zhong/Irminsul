"""CoverageCheck — every tier-3 doc must declare at least one valid test path."""

from __future__ import annotations

from pathlib import Path
from typing import ClassVar

from irminsul.checks.base import Finding, Severity
from irminsul.docgraph import DocGraph

CODE_MISSING_TESTS_ENTRY = "coverage/missing-tests-entry"
CODE_TESTS_PATH_MISSING = "coverage/tests-path-missing"


class CoverageCheck:
    name: ClassVar[str] = "coverage"
    default_severity: ClassVar[Severity] = Severity.error
    explanations: ClassVar[dict[str, str]] = {
        CODE_MISSING_TESTS_ENTRY: (
            "A tier-3 doc with a `describes` claim has no `tests:` entries. Add "
            "`tests: [path/to/test_file.py]` to frontmatter."
        ),
        CODE_TESTS_PATH_MISSING: (
            "A frontmatter `tests:` entry points at a path that does not exist. Create "
            "the test file, or update/remove the entry."
        ),
    }

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
                        code=CODE_MISSING_TESTS_ENTRY,
                        severity=self.default_severity,
                        message="tier-3 doc has no 'tests:' entries in frontmatter",
                        path=node.path,
                        doc_id=node.id,
                        suggestion="Add `tests: [path/to/test_file.py]` to frontmatter",
                        data={"problem": "missing-tests-entry", "field": "tests"},
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
                            code=CODE_TESTS_PATH_MISSING,
                            severity=self.default_severity,
                            message=f"tests: entry '{test_path}' does not exist",
                            path=node.path,
                            doc_id=node.id,
                            suggestion=f"Create '{test_path}' or update the tests: field",
                            data={
                                "problem": "tests-path-missing",
                                "field": "tests",
                                "value": test_path,
                            },
                        )
                    )

        return out
