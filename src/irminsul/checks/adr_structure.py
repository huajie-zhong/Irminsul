"""ADR body-structure invariants (RFC 0023)."""

from __future__ import annotations

import re
from typing import ClassVar

from irminsul.checks.base import Finding, Severity
from irminsul.docgraph import DocGraph, DocNode
from irminsul.docgraph_index import Heading, extract_section
from irminsul.frontmatter import AudienceEnum

_REQUIRED_SECTIONS: tuple[tuple[str, str], ...] = (
    ("status", "## Status"),
    ("context", "## Context"),
    ("decision", "## Decision"),
    ("alternatives-considered", "## Alternatives Considered"),
    ("consequences", "## Consequences"),
)
_HTML_COMMENT_RE = re.compile(r"<!--.*?-->", re.DOTALL)
_MARKDOWN_DECORATION_RE = re.compile(r"[\s`*_>#.\-:;!?]+")
_DECISION_PLACEHOLDERS = frozenset(
    {
        "decision pending",
        "describe the decision",
        "not decided",
        "pending",
        "state the decision",
        "tbd",
        "todo",
    }
)


CODE_MISSING_SECTION = "adr-structure/missing-section"
CODE_DUPLICATE_SECTION = "adr-structure/duplicate-section"
CODE_EMPTY_DECISION = "adr-structure/empty-decision"


class AdrStructureCheck:
    name: ClassVar[str] = "adr-structure"
    default_severity: ClassVar[Severity] = Severity.warning
    explanations: ClassVar[dict[str, str]] = {
        CODE_MISSING_SECTION: (
            "An ADR is missing one of its required sections (Status, Context, Decision, "
            "Alternatives Considered, Consequences). Add it."
        ),
        CODE_DUPLICATE_SECTION: (
            "An ADR has more than one heading for the same required section. Combine "
            "the content into a single section."
        ),
        CODE_EMPTY_DECISION: (
            "An ADR's '## Decision' section is empty or only a placeholder. Record the "
            "concrete decision in active voice."
        ),
    }

    def run(self, graph: DocGraph) -> list[Finding]:
        out: list[Finding] = []
        for node in graph.nodes.values():
            if node.frontmatter.audience != AudienceEnum.adr:
                continue
            headings = graph.headings.get(node.id, [])
            by_slug = {
                slug: [
                    heading for heading in headings if heading.level == 2 and heading.slug == slug
                ]
                for slug, _ in _REQUIRED_SECTIONS
            }
            out.extend(self._section_findings(node, by_slug))
            decision_headings = by_slug["decision"]
            if decision_headings and not _has_substantive_decision(node):
                out.append(
                    Finding(
                        check=self.name,
                        code=CODE_EMPTY_DECISION,
                        category="empty-decision",
                        severity=self.default_severity,
                        message="ADR has an empty or placeholder-only '## Decision' section",
                        path=node.path,
                        doc_id=node.id,
                        line=decision_headings[0].line,
                        suggestion="record the concrete decision in active voice",
                    )
                )
        return out

    def _section_findings(
        self,
        node: DocNode,
        by_slug: dict[str, list[Heading]],
    ) -> list[Finding]:
        out: list[Finding] = []
        for slug, display in _REQUIRED_SECTIONS:
            matches = by_slug[slug]
            if not matches:
                out.append(
                    Finding(
                        check=self.name,
                        code=CODE_MISSING_SECTION,
                        category="missing-section",
                        severity=self.default_severity,
                        message=f"ADR is missing a '{display}' section",
                        path=node.path,
                        doc_id=node.id,
                        suggestion=f"add a single '{display}' section",
                    )
                )
                continue
            if len(matches) > 1:
                out.append(
                    Finding(
                        check=self.name,
                        code=CODE_DUPLICATE_SECTION,
                        category="duplicate-section",
                        severity=self.default_severity,
                        message=f"ADR has more than one '{display}' section",
                        path=node.path,
                        doc_id=node.id,
                        line=matches[1].line,
                        suggestion=f"combine the content into one '{display}' section",
                    )
                )
        return out


def _has_substantive_decision(node: DocNode) -> bool:
    section = extract_section(node.body, "decision")
    if section is None:
        return False
    raw = "\n".join(line for _, line in section.lines)
    without_comments = _HTML_COMMENT_RE.sub("", raw)
    normalized = _MARKDOWN_DECORATION_RE.sub(" ", without_comments).strip().casefold()
    return bool(normalized) and normalized not in _DECISION_PLACEHOLDERS
