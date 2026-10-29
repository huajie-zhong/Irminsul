"""ADR body-structure invariants.

A shape check, not a lifecycle engine: lifecycle state lives in structured frontmatter,
and the body's `## Status` is a human summary, so it is never interpreted here.
"""

from __future__ import annotations

from typing import ClassVar

from irminsul.checks.base import Finding, FindingClass, Severity, certain_severity
from irminsul.checks.sections import RequiredSection, section_gaps
from irminsul.docgraph import DocGraph, is_decision

_REQUIRED_SECTIONS: tuple[RequiredSection, ...] = (
    RequiredSection("status", "Status"),
    RequiredSection("context", "Context"),
    RequiredSection("decision", "Decision", substantive=True),
    RequiredSection("alternatives-considered", "Alternatives Considered"),
    RequiredSection("consequences", "Consequences"),
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
            "An ADR's '## Decision' section is empty, or holds only HTML comments or text "
            "marked `<!-- irminsul:placeholder -->`. Record the concrete decision in active "
            "voice."
        ),
    }
    classes: ClassVar[dict[str, FindingClass]] = {
        CODE_MISSING_SECTION: FindingClass.certain,
        CODE_DUPLICATE_SECTION: FindingClass.certain,
        CODE_EMPTY_DECISION: FindingClass.certain,
    }
    drafts_exempt: ClassVar[frozenset[str]] = frozenset({CODE_MISSING_SECTION, CODE_EMPTY_DECISION})

    def run(self, graph: DocGraph) -> list[Finding]:
        out: list[Finding] = []
        for node in graph.nodes.values():
            if not is_decision(node, graph.config):
                continue
            for gap in section_gaps(node, graph.headings.get(node.id, []), _REQUIRED_SECTIONS):
                heading = f"## {gap.section.title}"
                line = None if gap.line is None else node.file_line(gap.line)
                if gap.kind == "missing":
                    code = CODE_MISSING_SECTION
                    message = f"ADR is missing a '{heading}' section"
                    suggestion = f"add a single '{heading}' section"
                elif gap.kind == "duplicate":
                    code = CODE_DUPLICATE_SECTION
                    message = f"ADR has more than one '{heading}' section"
                    suggestion = f"combine the content into one '{heading}' section"
                else:
                    code = CODE_EMPTY_DECISION
                    message = f"ADR has an empty or placeholder-only '{heading}' section"
                    suggestion = "record the concrete decision in active voice"
                out.append(
                    Finding(
                        check=self.name,
                        code=code,
                        severity=certain_severity(node),
                        message=message,
                        path=node.path,
                        doc_id=node.id,
                        line=line,
                        suggestion=suggestion,
                    )
                )
        return out
