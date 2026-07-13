"""RfcResolutionCheck — RFC lifecycle invariants (RFC-0017).

Enforces that RFCs under `<docs_root>/80-evolution/rfcs/` move through their
lifecycle cleanly: accepted RFCs become stable records linked bidirectionally
to a decision doc, rejected and withdrawn RFCs carry rationale sections, and
in-flight RFCs that have blown past their target decision date get flagged.

The check is intentionally narrow: it verifies structural shape only. It does
not pass judgement on the substance of a decision.
"""

from __future__ import annotations

import datetime as _dt
from collections.abc import Callable
from pathlib import Path, PurePosixPath
from typing import ClassVar

from irminsul import clock
from irminsul.checks.base import Finding, Fix, Severity
from irminsul.docgraph import DocGraph, DocNode
from irminsul.docgraph_index import Heading
from irminsul.frontmatter import RfcStateEnum, StatusEnum
from irminsul.frontmatter_edit import set_value

_IN_FLIGHT = frozenset({RfcStateEnum.draft, RfcStateEnum.open, RfcStateEnum.fcp})

# Finding categories. `fixes()` keys on these, so the two with a remediation are
# named apart from the four without one.
_CAT_STATUS_NOT_STABLE = "status-not-stable"
_CAT_MISSING_SECTION = "missing-section"
_CAT_DANGLING_RESOLVED_BY = "dangling-resolved-by"
_CAT_MISSING_BACKLINK = "missing-backlink"
_CAT_RETAINED_QUESTIONS = "retained-unresolved-questions"
_CAT_STALE_TARGET_DATE = "stale-target-date"

# Terminal states and the scaffolding section a resolved RFC of that state must
# carry. The fix inserts the first listed heading; the check accepts any.
_TERMINAL_SECTIONS: dict[RfcStateEnum, tuple[str, ...]] = {
    RfcStateEnum.accepted: ("Resolution",),
    RfcStateEnum.rejected: ("Rejection Rationale", "Resolution"),
    RfcStateEnum.withdrawn: ("Withdrawal Rationale", "Resolution"),
}


class RfcResolutionCheck:
    name: ClassVar[str] = "rfc-resolution"
    default_severity: ClassVar[Severity] = Severity.warning

    def run(self, graph: DocGraph) -> list[Finding]:
        today = clock.today(graph.now)
        out: list[Finding] = []

        docs_root = graph.config.paths.docs_root.strip("/\\") if graph.config else "docs"
        rfc_prefix = f"{docs_root}/80-evolution/rfcs/" if docs_root else "80-evolution/rfcs/"

        for node in graph.nodes.values():
            if not node.path.as_posix().startswith(rfc_prefix):
                continue
            state = node.frontmatter.rfc_state
            if state is None:
                continue

            headings = graph.headings.get(node.id, [])

            if state == RfcStateEnum.accepted:
                out.extend(self._check_accepted(graph, node, headings))
            elif state == RfcStateEnum.rejected:
                out.extend(self._check_rejected(node, headings))
            elif state == RfcStateEnum.withdrawn:
                out.extend(self._check_withdrawn(node, headings))
            elif state in _IN_FLIGHT:
                out.extend(self._check_in_flight(node, today))

        return out

    def fixes(self, findings: list[Finding], graph: DocGraph) -> list[Fix]:
        """Align a resolved RFC's metadata scaffolding (RFC 0017).

        For an RFC already in a terminal `rfc_state`, set `status: stable` and
        insert the missing scaffolding section as a stub. Touches load-bearing
        metadata, so it requires `--confirm`. Each fix is gated on the finding
        category it remediates, never merely on the doc: an RFC's dangling
        `resolved_by` and its retained questions have no fix, and must not
        inherit fixability from a `status`/`section` finding on the same doc.
        """
        flagged = self._flagged_by_category(findings)
        if not flagged:
            return []

        docs_root = graph.config.paths.docs_root.strip("/\\") if graph.config else "docs"
        rfc_prefix = f"{docs_root}/80-evolution/rfcs/" if docs_root else "80-evolution/rfcs/"

        out: list[Fix] = []
        for node in graph.nodes.values():
            if not node.path.as_posix().startswith(rfc_prefix):
                continue
            state = node.frontmatter.rfc_state
            sections = _TERMINAL_SECTIONS.get(state) if state is not None else None
            if sections is None:
                continue

            if (
                node.id in flagged[_CAT_STATUS_NOT_STABLE]
                and node.frontmatter.status != StatusEnum.stable
            ):
                out.append(
                    Fix(
                        path=node.path,
                        description=f"set status: stable in {node.path.as_posix()}",
                        apply=_status_setter(StatusEnum.stable.value),
                        requires_confirm=True,
                    )
                )

            headings = graph.headings.get(node.id, [])
            if node.id in flagged[_CAT_MISSING_SECTION] and not any(
                _has_heading(headings, _slug(title)) for title in sections
            ):
                title = sections[0]
                out.append(
                    Fix(
                        path=node.path,
                        description=f"insert '## {title}' stub in {node.path.as_posix()}",
                        apply=_section_adder(title),
                        requires_confirm=True,
                    )
                )

        return out

    def _flagged_by_category(self, findings: list[Finding]) -> dict[str, set[str]]:
        flagged: dict[str, set[str]] = {_CAT_STATUS_NOT_STABLE: set(), _CAT_MISSING_SECTION: set()}
        for finding in findings:
            if finding.check != self.name or finding.doc_id is None:
                continue
            if finding.category in flagged:
                flagged[finding.category].add(finding.doc_id)
        return flagged if any(flagged.values()) else {}

    def _check_accepted(
        self, graph: DocGraph, node: DocNode, headings: list[Heading]
    ) -> list[Finding]:
        out: list[Finding] = []
        fm = node.frontmatter

        if fm.status != StatusEnum.stable:
            out.append(
                Finding(
                    check=self.name,
                    severity=Severity.warning,
                    message=(
                        f"RFC is rfc_state: accepted but status is "
                        f"'{fm.status.value}'; expected 'stable'"
                    ),
                    path=node.path,
                    doc_id=node.id,
                    suggestion="set status: stable",
                    category=_CAT_STATUS_NOT_STABLE,
                )
            )

        resolved_by = fm.resolved_by  # pydantic guarantees non-None here
        assert resolved_by is not None
        target_path = Path(PurePosixPath(resolved_by))
        target = graph.by_path.get(target_path)
        if target is None:
            out.append(
                Finding(
                    check=self.name,
                    severity=Severity.warning,
                    message=(
                        f"resolved_by points to '{resolved_by}' but no such "
                        f"doc was found in the graph"
                    ),
                    path=node.path,
                    doc_id=node.id,
                    suggestion=(
                        "check the path; resolved_by is a repo-relative POSIX "
                        "path to an existing decision doc"
                    ),
                    category=_CAT_DANGLING_RESOLVED_BY,
                )
            )
        else:
            back_linkers = graph.inbound_weak.get(node.id, set())
            if target.id not in back_linkers:
                out.append(
                    Finding(
                        check=self.name,
                        severity=Severity.warning,
                        message=(
                            f"resolved-by doc '{target.path.as_posix()}' does "
                            f"not link back to this RFC"
                        ),
                        path=target.path,
                        doc_id=target.id,
                        suggestion=(
                            f"add a markdown link to {node.path.as_posix()} "
                            f"in the decision doc body"
                        ),
                        category=_CAT_MISSING_BACKLINK,
                    )
                )

        if not _has_heading(headings, "resolution"):
            out.append(
                Finding(
                    check=self.name,
                    severity=Severity.warning,
                    message="accepted RFC is missing a '## Resolution' section",
                    path=node.path,
                    doc_id=node.id,
                    suggestion=(
                        "add a '## Resolution' section pointing to the "
                        "decision doc and summarising the outcome"
                    ),
                    category=_CAT_MISSING_SECTION,
                )
            )

        if _has_heading(headings, "unresolved-questions") and _section_empty(
            node.body, headings, "unresolved-questions"
        ):
            out.append(
                Finding(
                    check=self.name,
                    severity=Severity.warning,
                    message=("accepted RFC retains an empty '## Unresolved Questions' section"),
                    path=node.path,
                    doc_id=node.id,
                    suggestion=("remove the section or list explicit required update work"),
                    category=_CAT_RETAINED_QUESTIONS,
                )
            )

        return out

    def _check_rejected(self, node: DocNode, headings: list[Heading]) -> list[Finding]:
        out: list[Finding] = []
        if node.frontmatter.status != StatusEnum.stable:
            out.append(
                Finding(
                    check=self.name,
                    severity=Severity.warning,
                    message=(
                        f"RFC is rfc_state: rejected but status is "
                        f"'{node.frontmatter.status.value}'; expected 'stable'"
                    ),
                    path=node.path,
                    doc_id=node.id,
                    suggestion="set status: stable once the rejection rationale is recorded",
                    category=_CAT_STATUS_NOT_STABLE,
                )
            )
        if not (
            _has_heading(headings, "resolution") or _has_heading(headings, "rejection-rationale")
        ):
            out.append(
                Finding(
                    check=self.name,
                    severity=Severity.warning,
                    message=(
                        "rejected RFC is missing a '## Resolution' or "
                        "'## Rejection Rationale' section"
                    ),
                    path=node.path,
                    doc_id=node.id,
                    suggestion=("add a section explaining why the proposal was rejected"),
                    category=_CAT_MISSING_SECTION,
                )
            )
        return out

    def _check_withdrawn(self, node: DocNode, headings: list[Heading]) -> list[Finding]:
        out: list[Finding] = []
        if node.frontmatter.status != StatusEnum.stable:
            out.append(
                Finding(
                    check=self.name,
                    severity=Severity.warning,
                    message=(
                        f"RFC is rfc_state: withdrawn but status is "
                        f"'{node.frontmatter.status.value}'; expected 'stable'"
                    ),
                    path=node.path,
                    doc_id=node.id,
                    suggestion="set status: stable",
                    category=_CAT_STATUS_NOT_STABLE,
                )
            )
        if not (
            _has_heading(headings, "withdrawal-rationale") or _has_heading(headings, "resolution")
        ):
            out.append(
                Finding(
                    check=self.name,
                    severity=Severity.warning,
                    message=(
                        "withdrawn RFC is missing a '## Withdrawal Rationale' "
                        "or '## Resolution' section"
                    ),
                    path=node.path,
                    doc_id=node.id,
                    suggestion=("add a section recording why the proposal was withdrawn"),
                    category=_CAT_MISSING_SECTION,
                )
            )
        if _has_heading(headings, "unresolved-questions") and not _section_empty(
            node.body, headings, "unresolved-questions"
        ):
            out.append(
                Finding(
                    check=self.name,
                    severity=Severity.warning,
                    message=("withdrawn RFC retains a non-empty '## Unresolved Questions' section"),
                    path=node.path,
                    doc_id=node.id,
                    suggestion=(
                        "remove the section or fold remaining questions into "
                        "the withdrawal rationale"
                    ),
                    category=_CAT_RETAINED_QUESTIONS,
                )
            )
        return out

    def _check_in_flight(self, node: DocNode, today: _dt.date) -> list[Finding]:
        out: list[Finding] = []
        fm = node.frontmatter
        if fm.target_decision_date is not None:
            target = _dt.date.fromisoformat(fm.target_decision_date)
            if target < today:
                out.append(
                    Finding(
                        check=self.name,
                        severity=Severity.warning,
                        message=(
                            f"target_decision_date {fm.target_decision_date} "
                            f"is in the past for a {fm.rfc_state.value if fm.rfc_state else ''} RFC"
                        ),
                        path=node.path,
                        doc_id=node.id,
                        suggestion=("decide, withdraw, or update target_decision_date"),
                        category=_CAT_STALE_TARGET_DATE,
                    )
                )
        return out


def _has_heading(headings: list[Heading], slug: str) -> bool:
    return any(h.slug == slug for h in headings)


def _slug(title: str) -> str:
    from irminsul.docgraph_index import slugify

    return slugify(title)


def _status_setter(value: str) -> Callable[[str], str]:
    def apply(text: str) -> str:
        return set_value(text, "status", value)

    return apply


def _section_adder(title: str) -> Callable[[str], str]:
    def apply(text: str) -> str:
        return _append_section(text, title)

    return apply


def _append_section(text: str, title: str) -> str:
    """Append a stub `## {title}` section, idempotent on the rendered heading."""
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
    start = target.line  # 1-indexed line of the heading itself; body starts after it

    end = len(lines)
    for h in headings:
        if h.line <= target.line:
            continue
        if h.level <= target.level:
            end = h.line - 1
            break

    section_body = "\n".join(lines[start:end]).strip()
    return section_body == ""
