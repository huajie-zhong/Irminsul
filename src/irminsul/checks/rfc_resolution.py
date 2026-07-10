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
from irminsul.frontmatter import RFC_STATE_ALIASES, RfcStateEnum, StatusEnum, canonical_rfc_state
from irminsul.frontmatter_edit import set_value

# Terminal states and the scaffolding section a resolved RFC of that state must
# carry. The fix inserts the first listed heading; the check accepts any.
_TERMINAL_SECTIONS: dict[RfcStateEnum, tuple[str, ...]] = {
    RfcStateEnum.accepted: ("Resolution",),
    RfcStateEnum.implemented: ("Resolution",),
    RfcStateEnum.rejected: ("Rejection Rationale", "Resolution", "Withdrawal Rationale"),
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

            if state in RFC_STATE_ALIASES:
                out.append(self._deprecated_state_finding(node, state))

            if state in (RfcStateEnum.accepted, RfcStateEnum.implemented):
                out.extend(self._check_accepted(graph, node, headings))
            elif state == RfcStateEnum.rejected:
                out.extend(self._check_rejected(node, headings))
            elif state == RfcStateEnum.withdrawn:
                out.extend(self._check_withdrawn(node, headings))
            elif canonical_rfc_state(state) == RfcStateEnum.draft:
                out.extend(self._check_in_flight(node, today))

        return out

    def _deprecated_state_finding(self, node: DocNode, state: RfcStateEnum) -> Finding:
        canonical = canonical_rfc_state(state)
        return Finding(
            check=self.name,
            category="deprecated-rfc-state",
            severity=Severity.warning,
            message=(
                f"rfc_state '{state.value}' is deprecated (RFC 0029); "
                f"the canonical state is '{canonical.value}'"
            ),
            path=node.path,
            doc_id=node.id,
            suggestion=f"set rfc_state: {canonical.value} (irminsul fix --confirm can do this)",
        )

    def fixes(self, findings: list[Finding], graph: DocGraph) -> list[Fix]:
        """Align a resolved RFC's metadata scaffolding (RFC 0017).

        For an RFC already in a terminal `rfc_state`, set `status: stable` and
        insert the missing scaffolding section as a stub. Touches load-bearing
        metadata, so it requires `--confirm`. Gated on this check's findings.
        """
        flagged = {
            finding.doc_id
            for finding in findings
            if finding.check == self.name and finding.doc_id is not None
        }
        if not flagged:
            return []

        docs_root = graph.config.paths.docs_root.strip("/\\") if graph.config else "docs"
        rfc_prefix = f"{docs_root}/80-evolution/rfcs/" if docs_root else "80-evolution/rfcs/"

        out: list[Fix] = []
        for node in graph.nodes.values():
            if node.id not in flagged:
                continue
            if not node.path.as_posix().startswith(rfc_prefix):
                continue
            state = node.frontmatter.rfc_state

            if state in RFC_STATE_ALIASES:
                canonical = canonical_rfc_state(state)
                out.append(
                    Fix(
                        path=node.path,
                        description=(
                            f"set rfc_state: {canonical.value} (deprecated alias "
                            f"'{state.value}') in {node.path.as_posix()}"
                        ),
                        apply=_rfc_state_setter(canonical.value),
                        requires_confirm=True,
                    )
                )

            sections = _TERMINAL_SECTIONS.get(state) if state is not None else None
            if sections is None:
                continue

            if node.frontmatter.status != StatusEnum.stable:
                out.append(
                    Fix(
                        path=node.path,
                        description=f"set status: stable in {node.path.as_posix()}",
                        apply=_status_setter(StatusEnum.stable.value),
                        requires_confirm=True,
                    )
                )

            headings = graph.headings.get(node.id, [])
            if not any(_has_heading(headings, _slug(title)) for title in sections):
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

    def _check_accepted(
        self, graph: DocGraph, node: DocNode, headings: list[Heading]
    ) -> list[Finding]:
        out: list[Finding] = []
        fm = node.frontmatter
        state_label = fm.rfc_state.value if fm.rfc_state else "accepted"

        if fm.status != StatusEnum.stable:
            out.append(
                Finding(
                    check=self.name,
                    severity=Severity.warning,
                    message=(
                        f"RFC is rfc_state: {state_label} but status is "
                        f"'{fm.status.value}'; expected 'stable'"
                    ),
                    path=node.path,
                    doc_id=node.id,
                    suggestion="set status: stable",
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
                    )
                )

        if not _has_heading(headings, "resolution"):
            out.append(
                Finding(
                    check=self.name,
                    severity=Severity.warning,
                    message=f"{state_label} RFC is missing a '## Resolution' section",
                    path=node.path,
                    doc_id=node.id,
                    suggestion=(
                        "add a '## Resolution' section pointing to the "
                        "decision doc and summarising the outcome"
                    ),
                )
            )

        if _has_heading(headings, "unresolved-questions") and _section_empty(
            node.body, headings, "unresolved-questions"
        ):
            out.append(
                Finding(
                    check=self.name,
                    severity=Severity.warning,
                    message=(
                        f"{state_label} RFC retains an empty '## Unresolved Questions' section"
                    ),
                    path=node.path,
                    doc_id=node.id,
                    suggestion=("remove the section or list explicit required update work"),
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
                )
            )
        # `withdrawal-rationale` stays accepted for RFCs canonicalized from the
        # deprecated `withdrawn` state (RFC 0029 deprecation window).
        if not (
            _has_heading(headings, "resolution")
            or _has_heading(headings, "rejection-rationale")
            or _has_heading(headings, "withdrawal-rationale")
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


def _rfc_state_setter(value: str) -> Callable[[str], str]:
    def apply(text: str) -> str:
        return set_value(text, "rfc_state", value)

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
