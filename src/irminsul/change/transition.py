"""`change transition`: apply a human-authorized decision atomically.

Acceptance and rejection are human decisions; this module only validates that
the transition is mechanically legal and applies every coupled edit in one
confirmed pass — `rfc_state`, `status: stable`, `resolved_by`, an empty
`required_updates`, and the terminal scaffolding section — reusing the dry-run/
confirm contract of `irminsul fix`.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from irminsul.change.gate import Issue, step_gate
from irminsul.change.report import ChangeError, find_rfc_node
from irminsul.checks.base import Fix
from irminsul.checks.rfc_follow_through import links_back, section_fixes, stable_status_fixes
from irminsul.config import IrminsulConfig
from irminsul.docgraph import DocGraph, DocNode
from irminsul.frontmatter import (
    RFC_DECIDED_STATES,
    RFC_STATE_TRANSITIONS,
    RequiredUpdateEntry,
    RfcStateEnum,
    entry_shape,
)
from irminsul.frontmatter_edit import setter


@dataclass(frozen=True)
class TransitionPlan:
    change: str
    path: Path
    current_state: str
    target_state: str
    blockers: tuple[Issue, ...]
    fixes: tuple[Fix, ...]
    notes: tuple[str, ...] = ()


def plan_transition(
    graph: DocGraph,
    config: IrminsulConfig,
    change: str,
    target: str,
    *,
    resolved_by: str | None = None,
) -> TransitionPlan:
    try:
        target_state = RfcStateEnum(target)
    except ValueError:
        raise ChangeError(
            f"unknown target state '{target}'; expected accepted or rejected"
        ) from None
    if target_state not in RFC_DECIDED_STATES:
        raise ChangeError(
            "change transition applies human decisions only (accepted or rejected); "
            "`implemented` is written exclusively by `change finalize`"
        )

    node = find_rfc_node(graph, config, change)
    fm = node.frontmatter
    assert fm.rfc_state is not None

    blockers: list[Issue] = []
    notes: list[str] = []
    rfc_path = node.path.as_posix()

    if target_state not in RFC_STATE_TRANSITIONS.get(fm.rfc_state, frozenset()):
        blockers.append(
            Issue(
                code="invalid-transition",
                message=(
                    f"cannot transition {fm.rfc_state.value} -> {target_state.value}; "
                    f"valid next states: "
                    f"{', '.join(sorted(s.value for s in RFC_STATE_TRANSITIONS[fm.rfc_state])) or '(none)'}"
                ),
                path=rfc_path,
            )
        )

    effective_resolved_by = resolved_by or fm.resolved_by
    if target_state == RfcStateEnum.rejected and resolved_by:
        blockers.append(
            Issue(
                code="unsupported-resolved-by",
                message=(
                    "--resolved-by applies to acceptance only; a rejection records its "
                    "rationale in the RFC body"
                ),
                path=rfc_path,
                suggestion="drop --resolved-by, or transition to accepted instead",
            )
        )
    blockers.extend(
        step_gate(graph, node, target_state, None, resolved_by=effective_resolved_by).issues
    )
    adr = graph.doc_at(effective_resolved_by) if effective_resolved_by else None
    if (
        target_state == RfcStateEnum.accepted
        and adr is not None
        and not links_back(graph, adr, node)
    ):
        notes.append(
            f"decision doc '{effective_resolved_by}' does not yet link back to "
            "this RFC; rfc-follow-through reports it until it does"
        )

    fixes: list[Fix] = []
    if not blockers:
        fixes.append(_set_fix(node, "rfc_state", target_state.value))
        fixes.extend(stable_status_fixes(node))
        if target_state == RfcStateEnum.accepted:
            if resolved_by and resolved_by != fm.resolved_by:
                fixes.append(_set_fix(node, "resolved_by", resolved_by))
            if fm.required_updates is None:
                fixes.append(_set_fix(node, "required_updates", [], "add required_updates: []"))
                notes.append(
                    "required_updates starts empty; list each downstream doc as a mapping with "
                    f"the keys {entry_shape(RequiredUpdateEntry)}"
                )
        fixes.extend(section_fixes(graph, node, target_state))

    return TransitionPlan(
        change=node.id,
        path=node.path,
        current_state=fm.rfc_state.value,
        target_state=target_state.value,
        blockers=tuple(blockers),
        fixes=tuple(fixes),
        notes=tuple(notes),
    )


def _set_fix(node: DocNode, key: str, value: object, description: str | None = None) -> Fix:
    return Fix(
        path=node.path,
        description=f"{description or f'set {key}: {value}'} in {node.path.as_posix()}",
        apply=setter(key, value),
        requires_confirm=True,
    )
