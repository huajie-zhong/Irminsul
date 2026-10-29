"""RfcStructureCheck — an RFC's owner's part comes first, in the shape its weight asks for.

An RFC has two readers. The owner decides whether it should happen and reads the sections
above `## Design detail`; the agent that implements it reads from `## Design detail` on. The
frontmatter `weight` says how much the owner reads: a `small` RFC is a sign-off with a Summary
and Decisions, a `large` one adds Problem, How it works and Cost and risk. The check reports
a missing weight, an owner's section the weight requires that is absent or empty, an owner's
section placed below `## Design detail`, and, as a hint, an owner's paragraph with four or more
code spans: a countable sign of a list of names that belongs below, not a judgement of the prose.

Only a draft or accepted RFC is judged. An implemented or rejected one is a sealed record, and
the layout is not asked of what was written before it existed. The weight is never inferred from
the body: a wrong one is for the owner to correct, so an RFC with none or an unknown one is asked
only for its weight.
"""

from __future__ import annotations

from collections import Counter
from typing import ClassVar

from irminsul.checks.base import (
    Answer,
    Finding,
    FindingClass,
    Severity,
    carries_certain_findings,
    certain_severity,
)
from irminsul.checks.code_spans import code_spans
from irminsul.checks.sections import RequiredSection, section_gaps
from irminsul.docgraph import DocGraph, DocNode, rfc_nodes
from irminsul.frontmatter import RFC_OPEN_STATES

CODE_MISSING_WEIGHT = "rfc-structure/missing-weight"
CODE_MISSING_SECTION = "rfc-structure/missing-section"
CODE_SECTION_OUT_OF_ORDER = "rfc-structure/section-out-of-order"
CODE_DENSE_PARAGRAPH = "rfc-structure/dense-paragraph"

DENSE_SPANS = 4
"""Code spans in one paragraph of the owner's part at which the hint fires."""

_OWNERS: tuple[RequiredSection, ...] = (
    RequiredSection("summary", "Summary", substantive=True),
    RequiredSection("problem", "Problem", substantive=True),
    RequiredSection("how-it-works", "How it works", substantive=True),
    RequiredSection("cost-and-risk", "Cost and risk", substantive=True),
    RequiredSection("decisions", "Decisions", substantive=True),
)
_REQUIRED_BY_WEIGHT: dict[str, tuple[RequiredSection, ...]] = {
    "small": tuple(s for s in _OWNERS if s.slug in {"summary", "decisions"}),
    "large": _OWNERS,
}
_DESIGN_DETAIL = "design-detail"
_AGENT_SLUGS = frozenset({_DESIGN_DETAIL, "requirements", "tasks", "resolution"})


class RfcStructureCheck:
    name: ClassVar[str] = "rfc-structure"
    default_severity: ClassVar[Severity] = Severity.warning
    explanations: ClassVar[dict[str, str]] = {
        CODE_MISSING_WEIGHT: (
            "A draft or accepted RFC has no `weight` in its frontmatter, or one other than "
            "`small` or `large`. Set `weight: small` for a sign-off the owner reads in seconds, "
            "or `weight: large` for a change that moves a decision or the foundation, breaks "
            "adopters, adds or removes a check or a command, or migrates data or history. The "
            "author proposes the weight and the owner may change it."
        ),
        CODE_MISSING_SECTION: (
            "A draft or accepted RFC lacks an owner's section its weight requires, or leaves "
            "it empty apart from comments and marked prompts. A small RFC needs Summary and "
            "Decisions; a large one needs Summary, Problem, How it works, Cost and risk and "
            "Decisions. Write the section for the owner, in plain words."
        ),
        CODE_SECTION_OUT_OF_ORDER: (
            "An owner's section sits below `## Design detail`, or an RFC has `## Requirements` "
            "but no `## Design detail` above it. The owner reads from the top and stops where "
            "the agent's part starts, so move the owner's section above `## Design detail`, "
            "and put the agent's part under it."
        ),
        CODE_DENSE_PARAGRAPH: (
            "A paragraph of the owner's part holds four or more code spans, which usually "
            "means a list of names, files or ids that an agent needs and an owner skims. Move "
            "the names under `## Design detail` and say in the owner's part what they add up "
            "to."
        ),
    }
    classes: ClassVar[dict[str, FindingClass]] = {
        CODE_MISSING_WEIGHT: FindingClass.certain,
        CODE_MISSING_SECTION: FindingClass.certain,
        CODE_SECTION_OUT_OF_ORDER: FindingClass.certain,
        CODE_DENSE_PARAGRAPH: FindingClass.hint,
    }
    answers: ClassVar[dict[str, Answer]] = {
        CODE_DENSE_PARAGRAPH: Answer.line(
            "a paragraph that needs its names keeps a reasoned ignore comment on its line"
        ),
    }
    drafts_exempt: ClassVar[frozenset[str]] = frozenset({CODE_MISSING_WEIGHT, CODE_MISSING_SECTION})

    def run(self, graph: DocGraph) -> list[Finding]:
        out: list[Finding] = []
        for node in rfc_nodes(graph).values():
            if node.frontmatter.rfc_state not in RFC_OPEN_STATES:
                continue
            if not carries_certain_findings(node):
                continue
            out.extend(self._weight_findings(node))
            out.extend(self._section_findings(graph, node))
            out.extend(self._order_findings(graph, node))
            out.extend(self._dense_findings(graph, node))
        return out

    def _weight_findings(self, node: DocNode) -> list[Finding]:
        weight = node.frontmatter.weight
        if weight in _REQUIRED_BY_WEIGHT:
            return []
        message = (
            "RFC has no weight"
            if weight is None
            else f"RFC has weight '{weight}', which is neither small nor large"
        )
        return [
            Finding(
                check=self.name,
                code=CODE_MISSING_WEIGHT,
                severity=certain_severity(node),
                message=message,
                path=node.path,
                doc_id=node.id,
                suggestion="set `weight: small` for a sign-off or `weight: large` for the "
                "five owner's sections",
            )
        ]

    def _section_findings(self, graph: DocGraph, node: DocNode) -> list[Finding]:
        weight = node.frontmatter.weight
        required = _REQUIRED_BY_WEIGHT.get(weight or "")
        if required is None:
            return []
        out: list[Finding] = []
        for gap in section_gaps(node, graph.headings.get(node.id, []), required):
            if gap.kind == "duplicate":
                continue
            heading = f"## {gap.section.title}"
            what = "is missing a" if gap.kind == "missing" else "has an empty or placeholder-only"
            out.append(
                Finding(
                    check=self.name,
                    code=CODE_MISSING_SECTION,
                    severity=certain_severity(node),
                    message=f"RFC {what} '{heading}' section its {weight} weight requires",
                    path=node.path,
                    doc_id=node.id,
                    line=None if gap.line is None else node.file_line(gap.line),
                    suggestion=f"write the '{heading}' section for the owner, in plain words",
                )
            )
        return out

    def _order_findings(self, graph: DocGraph, node: DocNode) -> list[Finding]:
        headings = [h for h in graph.headings.get(node.id, []) if h.level == 2]
        design = next((h for h in headings if h.slug == _DESIGN_DETAIL), None)
        if design is None:
            requirements = next((h for h in headings if h.slug == "requirements"), None)
            if requirements is None:
                return []
            return [
                Finding(
                    check=self.name,
                    code=CODE_SECTION_OUT_OF_ORDER,
                    severity=Severity.error,
                    message="RFC has '## Requirements' but no '## Design detail' above it",
                    path=node.path,
                    doc_id=node.id,
                    line=node.file_line(requirements.line),
                    suggestion="add '## Design detail' after the owner's sections, where the "
                    "agent's part starts",
                )
            ]
        owners = {section.slug for section in _OWNERS}
        return [
            Finding(
                check=self.name,
                code=CODE_SECTION_OUT_OF_ORDER,
                severity=Severity.error,
                message=f"'## {heading.text}' is an owner's section below '## Design detail'",
                path=node.path,
                doc_id=node.id,
                line=node.file_line(heading.line),
                suggestion=f"move '## {heading.text}' above '## Design detail'",
            )
            for heading in headings
            if heading.slug in owners and heading.line > design.line
        ]

    def _dense_findings(self, graph: DocGraph, node: DocNode) -> list[Finding]:
        agent_start = min(
            (
                h.line
                for h in graph.headings.get(node.id, [])
                if h.level == 2 and h.slug in _AGENT_SLUGS
            ),
            default=None,
        )
        spans = Counter(span.body_line for span in code_spans(node.body) if not span.fenced)
        out: list[Finding] = []
        for token in node.tokens:
            if token.type != "paragraph_open" or token.map is None:
                continue
            first, end = token.map[0] + 1, token.map[1]
            if agent_start is not None and first >= agent_start:
                break
            count = sum(spans[line] for line in range(first, end + 1))
            if count < DENSE_SPANS:
                continue
            out.append(
                Finding(
                    check=self.name,
                    code=CODE_DENSE_PARAGRAPH,
                    severity=Severity.warning,
                    message=f"paragraph in the owner's part holds {count} code spans",
                    path=node.path,
                    doc_id=node.id,
                    line=node.file_line(first),
                    suggestion="move the names under '## Design detail'",
                )
            )
        return out
