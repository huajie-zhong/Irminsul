"""BoundaryCheck — docs in a layer with `require_scope_section` declare what they do NOT do."""

from __future__ import annotations

import re
from typing import ClassVar

from irminsul.checks.base import Finding, FindingClass, Severity, certain_severity
from irminsul.docgraph import DocGraph, layer_rules

_REQUIRED_HEADING = "scope & limitations"

CODE_MISSING_SCOPE_LIMITATIONS = "boundary/missing-scope-limitations"
CODE_UNFILLED_SCOPE_SECTION = "boundary/unfilled-scope-section"

#: A section whose only content is an HTML comment is the scaffold's own prompt, still
#: waiting to be answered. `irminsul new component` writes one; so do the other `new`
#: templates. Matching the shape rather than the wording catches a prompt somebody
#: reworded, and a section a person emptied by hand.
# A level-two heading, as CommonMark accepts one: `##` then a space, a tab, or the end of
# the line. `\n## ` missed a tab-separated heading; requiring the newline then missed a
# heading that *starts* the remainder, which is what an empty scope section immediately
# followed by the next heading looks like. `^` under MULTILINE matches both.
_NEXT_HEADING = re.compile(r"^##(?=[ \t]|$)", re.MULTILINE)
_COMMENT_ONLY = re.compile(r"<!--.*?-->", re.DOTALL)


class BoundaryCheck:
    name: ClassVar[str] = "boundary"
    default_severity: ClassVar[Severity] = Severity.warning
    explanations: ClassVar[dict[str, str]] = {
        CODE_MISSING_SCOPE_LIMITATIONS: (
            "A doc in a layer that requires it has no '## Scope & Limitations' section. "
            "Add one describing what the component does NOT do."
        ),
        CODE_UNFILLED_SCOPE_SECTION: (
            "A doc's '## Scope & Limitations' section is empty, or holds only the comment "
            "the scaffold left there to prompt you. The heading being present is not the "
            "point of the rule — `irminsul context` reads this section out to an agent as "
            "what the component does not do, so an unanswered prompt is served as if it "
            "were knowledge. Answer it, or say plainly that nothing is out of scope."
        ),
    }
    classes: ClassVar[dict[str, FindingClass]] = {
        CODE_MISSING_SCOPE_LIMITATIONS: FindingClass.certain,
        CODE_UNFILLED_SCOPE_SECTION: FindingClass.certain,
    }
    drafts_exempt: ClassVar[frozenset[str]] = frozenset(
        {CODE_MISSING_SCOPE_LIMITATIONS, CODE_UNFILLED_SCOPE_SECTION}
    )

    def run(self, graph: DocGraph) -> list[Finding]:
        out: list[Finding] = []
        for node in graph.nodes.values():
            rules = layer_rules(node, graph.config)
            if rules is None or not rules[1].require_scope_section:
                continue
            headings = graph.headings.get(node.id, [])
            if not any(_REQUIRED_HEADING in h.text.lower() for h in headings):
                out.append(
                    Finding(
                        check=self.name,
                        code=CODE_MISSING_SCOPE_LIMITATIONS,
                        severity=certain_severity(node),
                        message=f"{rules[0]} doc is missing '## Scope & Limitations' section",
                        path=node.path,
                        doc_id=node.id,
                        suggestion="Add a '## Scope & Limitations' section describing what this component does NOT do",
                    )
                )
            elif not _answered(node.body):
                out.append(
                    Finding(
                        check=self.name,
                        code=CODE_UNFILLED_SCOPE_SECTION,
                        severity=certain_severity(node),
                        message=(
                            f"{rules[0]} doc has a '## Scope & Limitations' heading with "
                            "nothing under it but the scaffold's prompt"
                        ),
                        path=node.path,
                        doc_id=node.id,
                        suggestion=(
                            "say what this component does not do; `irminsul context` reads "
                            "this section out to an agent as if it were an answer"
                        ),
                    )
                )
        return out


def _answered(body: str) -> bool:
    """Whether the boundary section says anything a reader could act on.

    Only the last `## Scope & Limitations` heading's own text is read, and only down to
    the next heading of the same level, so prose under a later section does not stand in
    for an empty one.
    """
    lowered = body.lower()
    marker = lowered.rfind(f"## {_REQUIRED_HEADING}")
    if marker == -1:
        return True  # no section here; the missing-section rule already covers that
    section = body[marker:]
    newline = section.find("\n")
    if newline == -1:
        return False
    rest = section[newline + 1 :]
    if (match := _NEXT_HEADING.search(rest)) is not None:
        rest = rest[: match.start()]
    return bool(_COMMENT_ONLY.sub("", rest).strip())
