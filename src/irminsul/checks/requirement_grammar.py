"""RequirementGrammarCheck — structured review contracts on RFCs (RFC 0030).

Validates the shape of a `## Requirements` section: stable unique ids, SHALL/
MUST behavior text, named scenarios with WHEN and THEN, and a supported
evidence class per requirement. An RFC with no behavioral change instead
writes an explicit no-new-behavior disposition; mixing both is flagged.

Grammar proves structure only — it cannot decide whether a requirement is
useful, complete, or implemented. Malformed drafts produce warnings here;
`change transition ... accepted` treats the same findings as blockers because
acceptance freezes the contract to implement.
"""

from __future__ import annotations

import re
from typing import ClassVar

from irminsul.checks.base import Finding, Severity
from irminsul.docgraph import DocGraph, DocNode
from irminsul.docgraph_index import RequirementsSection
from irminsul.docgraph_index import Task as TaskType

# Evidence classes shared with claim provenance (RFC 0010 / RFC 0030).
PROVENANCE_CLASSES = ("code", "adr", "citation")

_REQ_ID_RE = re.compile(r"^[a-z][a-z0-9-]*$")


def requirement_grammar_findings(
    node: DocNode, section: RequirementsSection, *, check_name: str
) -> list[Finding]:
    """Grammar findings for one doc's parsed requirements section.

    Shared by the soft check (warnings) and the transition planner (blockers)
    so both always agree on what "well-formed" means.
    """
    out: list[Finding] = []

    def finding(category: str, message: str, line: int, suggestion: str) -> Finding:
        return Finding(
            check=check_name,
            category=category,
            severity=Severity.warning,
            message=message,
            path=node.path,
            doc_id=node.id,
            line=line,
            suggestion=suggestion,
        )

    if section.disposition is not None and section.requirements:
        out.append(
            finding(
                "mixed-disposition",
                "requirements section mixes an explicit no-new-behavior disposition "
                "with requirement blocks",
                section.line,
                "remove the disposition sentence or the requirement blocks",
            )
        )

    if section.disposition is None and not section.requirements:
        out.append(
            finding(
                "empty-requirements",
                "requirements section declares neither a requirement nor an explicit "
                "no-new-behavior disposition",
                section.line,
                "add `### Requirement:` blocks or the sentence "
                "'No new behavioral requirements: ...'",
            )
        )

    seen_ids: dict[str, int] = {}
    for req in section.requirements:
        label = f"requirement '{req.title}'"

        if req.req_id is None:
            out.append(
                finding(
                    "missing-id",
                    f"{label} has no `ID:` line",
                    req.line,
                    "add a stable kebab-case id, e.g. `ID: sso-login`",
                )
            )
        elif not _REQ_ID_RE.match(req.req_id):
            out.append(
                finding(
                    "invalid-id",
                    f"{label} has id '{req.req_id}' that is not a kebab-case slug",
                    req.line,
                    "use lowercase letters, digits, and dashes, starting with a letter",
                )
            )
        elif req.req_id in seen_ids:
            out.append(
                finding(
                    "duplicate-id",
                    f"requirement id '{req.req_id}' is already used at line {seen_ids[req.req_id]}",
                    req.line,
                    "requirement ids must be unique within the RFC",
                )
            )
        else:
            seen_ids[req.req_id] = req.line

        if req.provenance is None:
            out.append(
                finding(
                    "missing-provenance",
                    f"{label} has no `Provenance:` line",
                    req.line,
                    f"declare the evidence obligation: one of {', '.join(PROVENANCE_CLASSES)}",
                )
            )
        elif req.provenance not in PROVENANCE_CLASSES:
            out.append(
                finding(
                    "invalid-provenance",
                    f"{label} has provenance '{req.provenance}'; expected one of "
                    f"{', '.join(PROVENANCE_CLASSES)}",
                    req.line,
                    "use `code`, `adr`, or `citation`",
                )
            )

        if not req.has_behavior_keyword:
            out.append(
                finding(
                    "missing-behavior",
                    f"{label} contains no SHALL or MUST behavior text",
                    req.line,
                    "state the behavioral promise with SHALL or MUST",
                )
            )

        if not req.scenarios:
            out.append(
                finding(
                    "missing-scenario",
                    f"{label} has no named scenario",
                    req.line,
                    "add at least one `#### Scenario:` block with WHEN and THEN",
                )
            )
        for scenario in req.scenarios:
            missing = [
                keyword
                for keyword, present in (("WHEN", scenario.has_when), ("THEN", scenario.has_then))
                if not present
            ]
            if missing:
                out.append(
                    finding(
                        "incomplete-scenario",
                        f"scenario '{scenario.name}' of {label} is missing {' and '.join(missing)}",
                        scenario.line,
                        "every scenario needs a WHEN condition and a THEN outcome",
                    )
                )

    return out


def task_grammar_findings(
    node: DocNode,
    tasks: tuple[TaskType, ...],
    section: RequirementsSection | None,
    *,
    check_name: str,
) -> list[Finding]:
    """Grammar findings for one doc's `## Tasks` section (RFC 0031).

    Task ids must be unique within the RFC; a `(req: ...)` reference must
    resolve to a requirement id declared in the same RFC and a
    `(component: ...)` reference to a declared affected component.
    """
    out: list[Finding] = []

    def finding(category: str, message: str, line: int, suggestion: str) -> Finding:
        return Finding(
            check=check_name,
            category=category,
            severity=Severity.warning,
            message=message,
            path=node.path,
            doc_id=node.id,
            line=line,
            suggestion=suggestion,
        )

    requirement_ids = {
        req.req_id for req in (section.requirements if section else ()) if req.req_id
    }
    declared_components = set(node.frontmatter.affects or [])

    seen: dict[str, int] = {}
    for task in tasks:
        if task.task_id in seen:
            out.append(
                finding(
                    "task-duplicate-id",
                    f"task id '{task.task_id}' is already used at line {seen[task.task_id]}",
                    task.line,
                    "task ids must be unique within the RFC",
                )
            )
        else:
            seen[task.task_id] = task.line

        if task.req_ref is not None and task.req_ref not in requirement_ids:
            out.append(
                finding(
                    "task-unresolved-req",
                    f"task '{task.task_id}' references requirement '{task.req_ref}' "
                    "which is not declared in this RFC",
                    task.line,
                    "use a requirement id from the `## Requirements` section",
                )
            )
        if task.component_ref is not None and task.component_ref not in declared_components:
            out.append(
                finding(
                    "task-unresolved-component",
                    f"task '{task.task_id}' references component '{task.component_ref}' "
                    "which is not declared in `affects`",
                    task.line,
                    "reference a component id listed in the RFC's `affects`",
                )
            )

    return out


class RequirementGrammarCheck:
    name: ClassVar[str] = "requirement-grammar"
    default_severity: ClassVar[Severity] = Severity.warning

    def run(self, graph: DocGraph) -> list[Finding]:
        docs_root = graph.config.paths.docs_root.strip("/\\") if graph.config else "docs"
        rfc_prefix = f"{docs_root}/80-evolution/rfcs/" if docs_root else "80-evolution/rfcs/"

        out: list[Finding] = []
        rfc_ids = {
            doc_id
            for doc_id in (*graph.requirements, *graph.tasks)
            if (node := graph.nodes.get(doc_id)) is not None
            and node.path.as_posix().startswith(rfc_prefix)
            and node.frontmatter.rfc_state is not None
        }
        for doc_id in sorted(rfc_ids):
            node = graph.nodes[doc_id]
            section = graph.requirements.get(doc_id)
            if section is not None:
                out.extend(requirement_grammar_findings(node, section, check_name=self.name))
            tasks = graph.tasks.get(doc_id)
            if tasks is not None:
                out.extend(task_grammar_findings(node, tasks, section, check_name=self.name))
        return out
