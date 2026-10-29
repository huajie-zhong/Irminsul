"""ParentChildCheck — INDEX.md structural invariants.

An INDEX.md auto-owns every sibling `.md` file in its folder. No explicit
`children:` declaration is required or supported, and an INDEX need not link
its siblings: the agent manifest lists every doc.

Two concerns:

1. **Broad-globs ban** — once a parent INDEX has on-disk siblings, its
   `describes:` field must not contain wildcards. Children narrow coverage;
   wildcards on the parent risk silent overlap.
2. **Length cap** — INDEX bodies over `length_warning_lines` (default 300) get
   a warning. INDEX is meant to be navigation, not exposition.
"""

from __future__ import annotations

from typing import ClassVar

from irminsul.checks.base import Answer, Finding, FindingClass, Severity
from irminsul.docgraph import DocGraph

_WILDCARD_CHARS = set("*?[")


def _has_wildcard(pattern: str) -> bool:
    return any(c in pattern for c in _WILDCARD_CHARS)


CODE_WILDCARD_WITH_CHILDREN = "parent-child/wildcard-with-children"
CODE_INDEX_TOO_LONG = "parent-child/index-too-long"


class ParentChildCheck:
    name: ClassVar[str] = "parent-child"
    default_severity: ClassVar[Severity] = Severity.warning
    explanations: ClassVar[dict[str, str]] = {
        CODE_WILDCARD_WITH_CHILDREN: (
            "A parent INDEX has on-disk sibling docs but still declares a wildcard "
            "`describes` pattern, risking silent overlap with the children's claims. "
            "Enumerate exact files, or drop the claim and let the children cover it."
        ),
        CODE_INDEX_TOO_LONG: (
            "An INDEX.md body exceeds the configured line threshold. INDEX is meant to "
            "be navigation, not exposition — move long-form content into a sibling doc."
        ),
    }
    classes: ClassVar[dict[str, FindingClass]] = {
        CODE_WILDCARD_WITH_CHILDREN: FindingClass.hint,
        CODE_INDEX_TOO_LONG: FindingClass.hint,
    }
    answers: ClassVar[dict[str, Answer]] = {
        CODE_WILDCARD_WITH_CHILDREN: Answer.fix(
            "list the exact files, or drop the claim and let the children cover them"
        ),
        CODE_INDEX_TOO_LONG: Answer.fix("move the long-form content into a sibling doc"),
    }

    def run(self, graph: DocGraph) -> list[Finding]:
        if graph.config is None:
            return []

        length_threshold = graph.config.checks.parent_child.length_warning_lines

        out: list[Finding] = []

        for index_node in graph.nodes.values():
            if index_node.path.name != "INDEX.md":
                continue

            folder = index_node.path.parent
            has_siblings = any(
                path.parent == folder and path.name != "INDEX.md" for path in graph.by_path
            )

            # Broad-globs ban: parents with siblings must claim narrowly.
            if has_siblings:
                for pattern in index_node.frontmatter.describes:
                    if _has_wildcard(pattern):
                        out.append(
                            Finding(
                                check=self.name,
                                code=CODE_WILDCARD_WITH_CHILDREN,
                                severity=Severity.warning,
                                message=(
                                    f"parent INDEX with children must not use wildcard "
                                    f"'describes' pattern: '{pattern}'"
                                ),
                                path=index_node.path,
                                doc_id=index_node.id,
                                suggestion=(
                                    "enumerate exact files, or remove the describes "
                                    "claim and let the children's claims cover it"
                                ),
                            )
                        )

            # Length cap.
            line_count = len(index_node.body.splitlines())
            if line_count > length_threshold:
                out.append(
                    Finding(
                        check=self.name,
                        code=CODE_INDEX_TOO_LONG,
                        severity=Severity.warning,
                        message=(
                            f"INDEX body is {line_count} lines (threshold "
                            f"{length_threshold}); INDEX should be navigation, "
                            "not exposition"
                        ),
                        path=index_node.path,
                        doc_id=index_node.id,
                        suggestion="move long-form content into a sibling doc",
                    )
                )

        return out
