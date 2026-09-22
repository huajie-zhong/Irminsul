"""FrontmatterCheck — required fields, enums, ID/filename agreement."""

from __future__ import annotations

import difflib
import re
from typing import ClassVar

from irminsul.checks.base import Finding, FindingClass, Severity
from irminsul.docgraph import DocGraph, DocNode
from irminsul.frontmatter import DocFrontmatter, expected_id_for

CODE_PARSE_ERROR = "frontmatter/parse-error"
CODE_MISSING_FRONTMATTER = "frontmatter/missing-frontmatter"
CODE_ID_MISMATCH = "frontmatter/id-mismatch"
CODE_DUPLICATE_ID = "frontmatter/duplicate-id"
CODE_MISSPELLED_FIELD = "frontmatter/misspelled-field"

_CANONICAL_FIELDS = tuple(DocFrontmatter.model_fields)


def _misspelled_fields(node: DocNode) -> list[tuple[str, str]]:
    """Unknown top-level keys that stand in for a canonical field the doc does not set.

    A project may add keys of its own, so an unknown key is only wrong when it reads as a
    canonical field spelled differently. That misspelling is not harmless: the field it
    meant to set stays at its default, and every check that reads the field goes quiet.
    """
    out: list[tuple[str, str]] = []
    for key in node.frontmatter.model_extra or {}:
        normalized = key.lower().replace("-", "_")
        match = difflib.get_close_matches(normalized, _CANONICAL_FIELDS, n=1, cutoff=0.8)
        if match and match[0] not in node.frontmatter.model_fields_set:
            out.append((key, match[0]))
    return out


def _key_line(graph: DocGraph, node: DocNode, key: str) -> int | None:
    if graph.repo_root is None:
        return None
    try:
        lines = (graph.repo_root / node.path).read_text(encoding="utf-8").splitlines()
    except (OSError, UnicodeDecodeError):
        return None
    pattern = re.compile(rf"^{re.escape(key)}\s*:")
    return next((number for number, line in enumerate(lines, 1) if pattern.match(line)), None)


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
            "(id, title, status, ...)."
        ),
        CODE_ID_MISMATCH: (
            "The frontmatter `id` must match the id derived from the file's path. "
            "Fix the `id` field or rename the file."
        ),
        CODE_DUPLICATE_ID: (
            "Two docs declare the same `id`. Ids must be unique across the doc graph; "
            "rename one of them."
        ),
        CODE_MISSPELLED_FIELD: (
            "A top-level key is a near miss of a canonical field the doc does not set, such "
            "as `desribes` for `describes`, so the field it meant to set is empty and the "
            "checks that read it report nothing. Spell the field correctly. A key of your own "
            "that happens to resemble a field needs a name that does not."
        ),
    }
    classes: ClassVar[dict[str, FindingClass]] = {
        CODE_PARSE_ERROR: FindingClass.certain,
        CODE_MISSING_FRONTMATTER: FindingClass.certain,
        CODE_ID_MISMATCH: FindingClass.certain,
        CODE_DUPLICATE_ID: FindingClass.certain,
        CODE_MISSPELLED_FIELD: FindingClass.certain,
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

        for node in graph.nodes.values():
            for key, expected in _misspelled_fields(node):
                out.append(
                    Finding(
                        check=self.name,
                        code=CODE_MISSPELLED_FIELD,
                        severity=Severity.error,
                        message=(
                            f"frontmatter key '{key}' looks like a misspelling of '{expected}', "
                            f"which this doc does not set"
                        ),
                        path=node.path,
                        doc_id=node.frontmatter.id,
                        line=_key_line(graph, node, key),
                        suggestion=f"rename '{key}' to '{expected}'",
                        data={"problem": "misspelled-field", "field": key, "expected": expected},
                    )
                )

        for dup_id, first_path, conflicting_path in graph.duplicate_ids:
            out.append(
                Finding(
                    check=self.name,
                    code=CODE_DUPLICATE_ID,
                    severity=Severity.error,
                    message=(f"duplicate id '{dup_id}' (also defined at {first_path.as_posix()})"),
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
