"""RfcFollowThroughCheck — the work an RFC's state leaves outstanding.

A resolved RFC reads as a finished record linked to its decision, its required
doc updates exist and point back once it is implemented, an in-flight RFC does
not sit past its target date, and live docs do not cite drafts or plans the RFC
has since resolved. None of this blocks: it is follow-through, not invariant.
"""

from __future__ import annotations

import datetime as _dt
import re
from collections.abc import Callable
from pathlib import Path, PurePosixPath
from typing import ClassVar

from irminsul import clock
from irminsul.checks.base import Finding, FindingClass, Fix, Severity
from irminsul.checks.code_spans import is_live_doc
from irminsul.config import IrminsulConfig, layer_prefix
from irminsul.docgraph import DocGraph, DocNode, rfc_nodes
from irminsul.docgraph_index import Heading, slugify
from irminsul.frontmatter import ClaimStateEnum, RfcStateEnum, StatusEnum
from irminsul.frontmatter_edit import list_adder, setter

CODE_STATUS_NOT_STABLE = "rfc-follow-through/status-not-stable"
CODE_MISSING_SECTION = "rfc-follow-through/missing-section"
CODE_ADR_MISSING_RFC_LINK = "rfc-follow-through/adr-missing-rfc-link"
CODE_RETAINED_QUESTIONS = "rfc-follow-through/retained-questions"
CODE_STALE_TARGET_DATE = "rfc-follow-through/stale-target-date"
CODE_ACCEPTED_NOT_IMPLEMENTED = "rfc-follow-through/accepted-not-implemented"
CODE_NO_REQUIRED_UPDATES_FIELD = "rfc-follow-through/no-required-updates-field"
CODE_MISSING_REQUIRED_UPDATE_PATH = "rfc-follow-through/missing-required-update-path"
CODE_UPDATE_MISSING_IMPLEMENTS = "rfc-follow-through/update-missing-implements"
CODE_STALE_CLAIM = "rfc-follow-through/stale-claim"
CODE_STABLE_DOC_LINKS_DRAFT_RFC = "rfc-follow-through/stable-doc-links-draft-rfc"

# The scaffolding section a resolved RFC of each state carries. The fix inserts
# the first listed heading; the check accepts any.
_TERMINAL_SECTIONS: dict[RfcStateEnum, tuple[str, ...]] = {
    RfcStateEnum.accepted: ("Resolution",),
    RfcStateEnum.implemented: ("Resolution",),
    RfcStateEnum.rejected: ("Rejection Rationale", "Resolution"),
}
_UPDATE_TRACKED_STATES = frozenset({RfcStateEnum.accepted, RfcStateEnum.implemented})
_RESOLVED_STATES = frozenset({*_UPDATE_TRACKED_STATES, RfcStateEnum.rejected})
# A `planned` claim stays true while its RFC is accepted but not yet built.
PLANNED_CLAIM_STALE_STATES = frozenset({RfcStateEnum.implemented, RfcStateEnum.rejected})


class RfcFollowThroughCheck:
    name: ClassVar[str] = "rfc-follow-through"
    default_severity: ClassVar[Severity] = Severity.warning
    explanations: ClassVar[dict[str, str]] = {
        CODE_STATUS_NOT_STABLE: (
            "A resolved RFC's `rfc_state` implies a terminal outcome but `status` is not "
            "`stable`. Set `status: stable`."
        ),
        CODE_MISSING_SECTION: (
            "A resolved RFC is missing the scaffolding section its state requires "
            "(Resolution or Rejection Rationale). Add it."
        ),
        CODE_ADR_MISSING_RFC_LINK: (
            "The decision doc named by `resolved_by` does not link back to the RFC. Add "
            "a markdown link to the RFC in the decision doc body."
        ),
        CODE_RETAINED_QUESTIONS: (
            "An accepted or implemented RFC retains an empty '## Unresolved Questions' "
            "section. Remove it or list the remaining work explicitly."
        ),
        CODE_STALE_TARGET_DATE: (
            "A draft RFC's `target_decision_date` is in the past. Decide, reject, or "
            "update `target_decision_date`."
        ),
        CODE_ACCEPTED_NOT_IMPLEMENTED: (
            "An RFC has been accepted, without change, for longer than "
            "`checks.rfc_follow_through.accepted_threshold_days`, and no doc it names in "
            "`affects` or `required_updates` has changed since. Implement and finalize it, "
            "or reject it."
        ),
        CODE_NO_REQUIRED_UPDATES_FIELD: (
            "An accepted or implemented RFC has no `required_updates` field. Add "
            "`required_updates: []` if no downstream docs need updating, or list the "
            "docs that must be created, updated, or reviewed."
        ),
        CODE_MISSING_REQUIRED_UPDATE_PATH: (
            "A `required_updates` path listed on the RFC does not exist in the graph. "
            "Create the doc or correct the path."
        ),
        CODE_UPDATE_MISSING_IMPLEMENTS: (
            "A required-update doc of an implemented RFC does not name it in "
            '`implements`. Add `implements: ["<rfc-id>"]` to the doc.'
        ),
        CODE_STALE_CLAIM: (
            "A `planned` claim cites an RFC that is now implemented or "
            "rejected. Update the claim's state to match reality."
        ),
        CODE_STABLE_DOC_LINKS_DRAFT_RFC: (
            "A stable, live doc links to a still-draft RFC. Verify the behavior is "
            "shipped and finalize the RFC, or stop presenting it as live."
        ),
    }
    classes: ClassVar[dict[str, FindingClass]] = {
        CODE_STATUS_NOT_STABLE: FindingClass.certain,
        CODE_MISSING_SECTION: FindingClass.certain,
        CODE_ADR_MISSING_RFC_LINK: FindingClass.certain,
        CODE_RETAINED_QUESTIONS: FindingClass.certain,
        CODE_STALE_TARGET_DATE: FindingClass.time,
        CODE_ACCEPTED_NOT_IMPLEMENTED: FindingClass.time,
        CODE_NO_REQUIRED_UPDATES_FIELD: FindingClass.certain,
        CODE_MISSING_REQUIRED_UPDATE_PATH: FindingClass.certain,
        CODE_UPDATE_MISSING_IMPLEMENTS: FindingClass.certain,
        CODE_STALE_CLAIM: FindingClass.certain,
        CODE_STABLE_DOC_LINKS_DRAFT_RFC: FindingClass.hint,
    }

    def run(self, graph: DocGraph) -> list[Finding]:
        today = clock.today(graph.now)
        out: list[Finding] = []
        for node in rfc_nodes(graph).values():
            state = node.frontmatter.rfc_state
            if state is None:
                continue
            headings = graph.headings.get(node.id, [])
            if state in _RESOLVED_STATES:
                out.extend(self._check_resolved(graph, node, state, headings))
            if state in _UPDATE_TRACKED_STATES:
                out.extend(self._check_required_updates(graph, node, state))
            if state == RfcStateEnum.draft:
                out.extend(self._check_draft(graph, node, today))
            if state == RfcStateEnum.accepted:
                out.extend(self._check_accepted(graph, node, today))
        for node in graph.nodes.values():
            out.extend(self._check_planned_claims(graph, node))
        return out

    def fixes(self, findings: list[Finding], graph: DocGraph) -> list[Fix]:
        """Set a resolved RFC's status, stub its missing section, and add missing
        `implements` back-links.

        Status and section edits touch load-bearing metadata and need `--confirm`;
        the back-link is a purely additive inverse pointer and applies by default.
        Each fix is gated on the finding category it remediates, never merely on
        the doc it names.
        """
        flagged: dict[str, set[str]] = {}
        for finding in findings:
            if finding.check == self.name and finding.doc_id is not None and finding.category:
                flagged.setdefault(finding.category, set()).add(finding.doc_id)
        if not flagged:
            return []

        out: list[Fix] = []
        for node in rfc_nodes(graph).values():
            state = node.frontmatter.rfc_state
            sections = _TERMINAL_SECTIONS.get(state) if state is not None else None
            if sections is not None:
                if (
                    node.id in flagged.get("status-not-stable", set())
                    and node.frontmatter.status != StatusEnum.stable
                ):
                    out.append(
                        Fix(
                            path=node.path,
                            description=f"set status: stable in {node.path.as_posix()}",
                            apply=setter("status", StatusEnum.stable.value),
                            requires_confirm=True,
                        )
                    )
                headings = graph.headings.get(node.id, [])
                if node.id in flagged.get("missing-section", set()) and not any(
                    has_heading(headings, slugify(title)) for title in sections
                ):
                    out.append(
                        Fix(
                            path=node.path,
                            description=f"insert '## {sections[0]}' stub in {node.path.as_posix()}",
                            apply=_section_adder(sections[0]),
                            requires_confirm=True,
                        )
                    )
            if state != RfcStateEnum.implemented:
                continue
            for target in self.missing_implements(graph, node):
                if target.id in flagged.get("update-missing-implements", set()):
                    out.append(
                        Fix(
                            path=target.path,
                            description=f"add implements: {node.id} to {target.path.as_posix()}",
                            apply=list_adder("implements", node.id),
                        )
                    )
        return out

    def _check_resolved(
        self, graph: DocGraph, node: DocNode, state: RfcStateEnum, headings: list[Heading]
    ) -> list[Finding]:
        out: list[Finding] = []
        fm = node.frontmatter
        if fm.status != StatusEnum.stable:
            out.append(
                _finding(
                    node,
                    CODE_STATUS_NOT_STABLE,
                    f"RFC is rfc_state: {state.value} but status is '{fm.status.value}'; "
                    "expected 'stable'",
                    "set status: stable",
                )
            )
        sections = _TERMINAL_SECTIONS[state]
        if not any(has_heading(headings, slugify(title)) for title in sections):
            names = " or ".join(f"'## {title}'" for title in reversed(sections))
            out.append(
                _finding(
                    node,
                    CODE_MISSING_SECTION,
                    f"{state.value} RFC is missing a {names} section",
                    "add the section summarising the outcome and linking the decision doc",
                )
            )
        if state == RfcStateEnum.rejected:
            return out

        target = graph.by_path.get(Path(PurePosixPath(fm.resolved_by))) if fm.resolved_by else None
        if target is not None and target.id not in graph.inbound_weak.get(node.id, set()):
            out.append(
                _finding(
                    target,
                    CODE_ADR_MISSING_RFC_LINK,
                    f"resolved-by doc '{target.path.as_posix()}' does not link back to RFC "
                    f"'{node.id}'",
                    f"add a markdown link to {node.path.as_posix()} in the decision doc body",
                )
            )
        if has_heading(headings, "unresolved-questions") and _section_empty(
            node.body, headings, "unresolved-questions"
        ):
            out.append(
                _finding(
                    node,
                    CODE_RETAINED_QUESTIONS,
                    f"{state.value} RFC retains an empty '## Unresolved Questions' section",
                    "remove the section or list explicit required update work",
                )
            )
        return out

    def _check_required_updates(
        self, graph: DocGraph, node: DocNode, state: RfcStateEnum
    ) -> list[Finding]:
        required_updates = node.frontmatter.required_updates
        if required_updates is None:
            return [
                _finding(
                    node,
                    CODE_NO_REQUIRED_UPDATES_FIELD,
                    f"{state.value} RFC has no `required_updates` field; add "
                    "`required_updates: []` if no downstream docs need updating",
                    "add `required_updates: []` or list docs that must be created/updated/reviewed",
                )
            ]
        out = [
            _finding(
                node,
                CODE_MISSING_REQUIRED_UPDATE_PATH,
                f"required update path '{entry.path}' listed on {state.value} RFC does not "
                "exist in the graph",
                "create the doc or correct the path in `required_updates`",
            )
            for entry in required_updates
            if graph.by_path.get(Path(PurePosixPath(entry.path))) is None
        ]
        if state == RfcStateEnum.implemented:
            out.extend(
                _finding(
                    target,
                    CODE_UPDATE_MISSING_IMPLEMENTS,
                    f"required update doc '{target.path.as_posix()}' does not link back to "
                    f"RFC '{node.id}' via `implements`",
                    f'add `implements: ["{node.id}"]` to {target.path.as_posix()}',
                )
                for target in self.missing_implements(graph, node)
            )
        return out

    def missing_implements(self, graph: DocGraph, node: DocNode) -> list[DocNode]:
        """Required-update docs that do not yet name this RFC in `implements`.

        The decision doc named by `resolved_by` records the decision rather than
        implementing it, so it is never asked for the back-link.
        """
        resolved_by = node.frontmatter.resolved_by
        decision = Path(PurePosixPath(resolved_by)) if resolved_by else None
        out: list[DocNode] = []
        for entry in node.frontmatter.required_updates or []:
            target = graph.by_path.get(Path(PurePosixPath(entry.path)))
            if target is None or target.path == decision:
                continue
            if node.id not in target.frontmatter.implements:
                out.append(target)
        return out

    def _check_accepted(self, graph: DocGraph, node: DocNode, today: _dt.date) -> list[Finding]:
        """An accepted RFC whose named docs have not changed since it did, for too long."""
        if graph.repo_root is None:
            return []
        from irminsul.git.mtime import last_commit_time_any_repo

        repo_root = graph.repo_root

        def committed(target: DocNode) -> _dt.datetime | None:
            found = last_commit_time_any_repo(repo_root / target.path, repo_root)
            return found.when if found is not None else None

        accepted_at = committed(node)
        if accepted_at is None:
            return []
        threshold = (graph.config or IrminsulConfig()).checks.rfc_follow_through
        age = (today - accepted_at.date()).days
        if age <= threshold.accepted_threshold_days:
            return []
        named = [graph.nodes.get(doc_id) for doc_id in node.frontmatter.affects or []]
        named += [
            graph.by_path.get(Path(PurePosixPath(entry.path)))
            for entry in node.frontmatter.required_updates or []
        ]
        for target in named:
            when = committed(target) if target is not None else None
            if when is not None and when >= accepted_at:
                return []
        return [
            _finding(
                node,
                CODE_ACCEPTED_NOT_IMPLEMENTED,
                f"RFC accepted and unchanged for {age} days, and no doc it names in `affects` "
                "or `required_updates` changed since",
                "implement it and finalize it with `irminsul change finalize`, or reject it",
            )
        ]

    def _check_draft(self, graph: DocGraph, node: DocNode, today: _dt.date) -> list[Finding]:
        out: list[Finding] = []
        target_date = node.frontmatter.target_decision_date
        if target_date is not None and _dt.date.fromisoformat(target_date) < today:
            out.append(
                _finding(
                    node,
                    CODE_STALE_TARGET_DATE,
                    f"target_decision_date {target_date} is in the past for a draft RFC",
                    "decide, reject, or update target_decision_date",
                )
            )
        for source_id in sorted(graph.inbound_weak.get(node.id, set())):
            source = graph.nodes.get(source_id)
            if source is None or not is_live_doc(source, graph.config):
                continue
            out.append(
                _finding(
                    source,
                    CODE_STABLE_DOC_LINKS_DRAFT_RFC,
                    f"stable live documentation links draft RFC '{node.id}'",
                    "verify the behavior is shipped and finalize the RFC, or stop presenting "
                    "it as live",
                    data={"rfc": node.id},
                )
            )
        return out

    def _check_planned_claims(self, graph: DocGraph, node: DocNode) -> list[Finding]:
        out: list[Finding] = []
        rfc_path_re = _rfc_path_re(graph)
        for claim in node.frontmatter.claims:
            if claim.state != ClaimStateEnum.planned:
                continue
            for evidence in claim.evidence:
                match = rfc_path_re.search(evidence)
                rfc = graph.by_path.get(Path(match.group(0))) if match else None
                state = rfc.frontmatter.rfc_state if rfc is not None else None
                if rfc is None or state not in PLANNED_CLAIM_STALE_STATES:
                    continue
                assert state is not None
                out.append(
                    _finding(
                        node,
                        CODE_STALE_CLAIM,
                        f"planned claim '{claim.id}' cites RFC '{rfc.id}' which is now "
                        f"{state.value}; update the claim state",
                        f"change claim '{claim.id}' state from 'planned' to 'implemented' "
                        "(or 'available' / 'enabled') once the feature is live",
                    )
                )
        return out


def _finding(
    node: DocNode,
    code: str,
    message: str,
    suggestion: str,
    *,
    data: dict[str, str] | None = None,
) -> Finding:
    category = code.split("/", 1)[1]
    return Finding(
        check=RfcFollowThroughCheck.name,
        code=code,
        category=category,
        severity=(
            Severity.error
            if RfcFollowThroughCheck.classes[code] is FindingClass.certain
            else Severity.warning
        ),
        message=message,
        path=node.path,
        doc_id=node.id,
        suggestion=suggestion,
        data={"problem": category, **(data or {})} if data else None,
    )


def _rfc_path_re(graph: DocGraph) -> re.Pattern[str]:
    """Repo-relative RFC paths named in claim evidence."""
    prefix = layer_prefix(graph.config or IrminsulConfig(), "rfcs")
    return re.compile(re.escape(prefix) + r"/[^/\s)]+\.md")


def has_heading(headings: list[Heading], slug: str) -> bool:
    return any(h.slug == slug for h in headings)


def _section_adder(title: str) -> Callable[[str], str]:
    def apply(text: str) -> str:
        return append_section(text, title)

    return apply


def append_section(text: str, title: str) -> str:
    """Append a stub `## {title}` section, unless the text already has that heading.

    The guard is over the raw lines rather than the rendered headings, because a heading
    inside an unclosed code fence renders as code: the caller then saw no heading, and
    every run appended another stub without the finding ever clearing.
    """
    heading = f"## {title}"
    if any(line.rstrip() == heading for line in text.splitlines()):
        return text
    stub = (
        f"## {title}\n\n<!-- TODO: record the decision rationale and link the decision doc. -->\n"
    )
    if text.endswith("\n\n"):
        sep = ""
    elif text.endswith("\n"):
        sep = "\n"
    else:
        sep = "\n\n"
    return f"{text}{sep}{stub}"


def _section_empty(body: str, headings: list[Heading], slug: str) -> bool:
    """True when the section under `slug` has only whitespace before the next
    heading of equal-or-lower level (or end of body)."""
    target = next((h for h in headings if h.slug == slug), None)
    if target is None:
        return True
    lines = body.splitlines()
    end = len(lines)
    for h in headings:
        if h.line > target.line and h.level <= target.level:
            end = h.line - 1
            break
    return "\n".join(lines[target.line : end]).strip() == ""
