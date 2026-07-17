"""FrontmatterCheck — required fields, enums, ID/filename agreement."""

from __future__ import annotations

from typing import ClassVar

from irminsul.checks.base import Finding, Severity
from irminsul.docgraph import DocGraph
from irminsul.frontmatter import expected_id_for

CODE_PARSE_ERROR = "frontmatter/parse-error"
CODE_MISSING_FRONTMATTER = "frontmatter/missing-frontmatter"
CODE_ID_MISMATCH = "frontmatter/id-mismatch"
CODE_DUPLICATE_ID = "frontmatter/duplicate-id"


class FrontmatterCheck:
    name: ClassVar[str] = "frontmatter"
    default_severity: ClassVar[Severity] = Severity.error
    explanations: ClassVar[dict[str, str]] = {
        CODE_PARSE_ERROR: (
            "The doc's YAML frontmatter failed to parse or failed schema validation. "
            "Fix the reported field so the block parses and validates."
        ),
        CODE_MISSING_FRONTMATTER: (
            "Every doc atom needs a frontmatter block. Add one with the required fields "
            "(id, title, status, audience, tier, ...)."
        ),
        CODE_ID_MISMATCH: (
            "The frontmatter `id` must match the id derived from the file's path. "
            "Fix the `id` field or rename the file."
        ),
        CODE_DUPLICATE_ID: (
            "Two docs declare the same `id`. Ids must be unique across the doc graph; "
            "rename one of them."
        ),
    }

    def run(self, graph: DocGraph) -> list[Finding]:
        out: list[Finding] = []

        for failure in graph.parse_failures:
            out.append(
                Finding(
                    check=self.name,
                    code=CODE_PARSE_ERROR,
                    severity=Severity.error,
                    message=f"frontmatter parse error: {failure.error}",
                    path=failure.path,
                    data=failure.data or {"problem": "parse-error"},
                )
            )

        for path in graph.missing_frontmatter:
            out.append(
                Finding(
                    check=self.name,
                    code=CODE_MISSING_FRONTMATTER,
                    severity=Severity.error,
                    message="missing frontmatter (required for every doc atom)",
                    path=path,
                    data={"problem": "missing-frontmatter"},
                )
            )

        for node in graph.nodes.values():
            expected = expected_id_for(node.path)
            if node.frontmatter.id != expected:
                out.append(
                    Finding(
                        check=self.name,
                        code=CODE_ID_MISMATCH,
                        severity=Severity.error,
                        message=(
                            f"id '{node.frontmatter.id}' does not match filename "
                            f"(expected '{expected}')"
                        ),
                        path=node.path,
                        doc_id=node.frontmatter.id,
                        data={
                            "problem": "id-mismatch",
                            "field": "id",
                            "value": node.frontmatter.id,
                            "expected": expected,
                        },
                    )
                )

        for dup_id, first_path, conflicting_path in graph.duplicate_ids:
            out.append(
                Finding(
                    check=self.name,
                    code=CODE_DUPLICATE_ID,
                    severity=Severity.error,
                    message=(f"duplicate id '{dup_id}' (also defined at {first_path})"),
                    path=conflicting_path,
                    doc_id=dup_id,
                    data={
                        "problem": "duplicate-id",
                        "field": "id",
                        "value": dup_id,
                        "other_path": first_path.as_posix(),
                    },
                )
            )

        return out
