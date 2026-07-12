"""`change transition` (RFC 0029): apply a human-authorized decision atomically.

Acceptance and rejection are human decisions; this module only validates that
the transition is mechanically legal and applies every coupled edit in one
confirmed pass — `rfc_state`, `status: stable`, `resolved_by`, an empty
`required_updates`, and the terminal scaffolding section — reusing the dry-run/
confirm contract of `irminsul fix`.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from irminsul.change.report import Blocker, ChangeError, find_rfc_node
from irminsul.checks.base import Fix
from irminsul.checks.rfc_resolution import _append_section, _has_heading
from irminsul.config import IrminsulConfig
from irminsul.docgraph import DocGraph
from irminsul.frontmatter import (
    RFC_STATE_TRANSITIONS,
    RfcStateEnum,
    StatusEnum,
    canonical_rfc_state,
)
from irminsul.frontmatter_edit import set_value

# Scaffolding section inserted when a transition leaves it missing.
_TARGET_SECTIONS: dict[RfcStateEnum, str] = {
    RfcStateEnum.accepted: "Resolution",
    RfcStateEnum.rejected: "Rejection Rationale",
}


@dataclass(frozen=True)
class TransitionPlan:
    change: str
    path: Path
    current_state: str
    target_state: str
    blockers: tuple[Blocker, ...]
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
            f"unknown target state '{target}'; expected accepted or rejected", code=2
        ) from None
    if target_state not in (RfcStateEnum.accepted, RfcStateEnum.rejected):
        raise ChangeError(
            "change transition applies human decisions only (accepted or rejected); "
            "`implemented` is written exclusively by `change finalize`",
            code=2,
        )

    node = find_rfc_node(graph, config, change)
    fm = node.frontmatter
    assert fm.rfc_state is not None
    canonical = canonical_rfc_state(fm.rfc_state)

    blockers: list[Blocker] = []
    notes: list[str] = []
    rfc_path = node.path.as_posix()

    if target_state not in RFC_STATE_TRANSITIONS.get(canonical, frozenset()):
        blockers.append(
            Blocker(
                code="invalid-transition",
                message=(
                    f"cannot transition {canonical.value} -> {target_state.value}; "
                    f"valid next states: "
                    f"{', '.join(sorted(s.value for s in RFC_STATE_TRANSITIONS[canonical])) or '(none)'}"
                ),
                path=rfc_path,
            )
        )

    effective_resolved_by = resolved_by or fm.resolved_by
    if target_state == RfcStateEnum.rejected and resolved_by:
        blockers.append(
            Blocker(
                code="unsupported-resolved-by",
                message=(
                    "--resolved-by applies to acceptance only; a rejection records its "
                    "rationale in the RFC body"
                ),
                path=rfc_path,
                suggestion="drop --resolved-by, or transition to accepted instead",
            )
        )
    if target_state == RfcStateEnum.accepted:
        if fm.affects is None:
            blockers.append(
                Blocker(
                    code="missing-affects",
                    message=(
                        "acceptance freezes intended scope: declare `affects` "
                        "explicitly (use [] when no owned source changes)"
                    ),
                    path=rfc_path,
                    suggestion="add `affects: [<component ids>]` to the RFC frontmatter",
                )
            )
        for declared in fm.affects or []:
            if declared not in graph.nodes:
                blockers.append(
                    Blocker(
                        code="unknown-component",
                        message=f"`affects` entry '{declared}' does not match any doc id",
                        path=rfc_path,
                    )
                )
        if not effective_resolved_by:
            blockers.append(
                Blocker(
                    code="missing-adr",
                    message="an accepted RFC must resolve to a decision record",
                    path=rfc_path,
                    suggestion=(
                        "create it with `irminsul new adr <title>` and pass "
                        "--resolved-by <adr path>"
                    ),
                )
            )
        else:
            adr = graph.by_path.get(Path(effective_resolved_by.replace("\\", "/")))
            if adr is None:
                blockers.append(
                    Blocker(
                        code="unresolved-adr",
                        message=(
                            f"resolved_by '{effective_resolved_by}' does not exist in the graph"
                        ),
                        path=rfc_path,
                    )
                )
            elif adr.id not in graph.inbound_weak.get(node.id, set()):
                notes.append(
                    f"decision doc '{effective_resolved_by}' does not yet link back to "
                    "this RFC; rfc-resolution will warn until it does"
                )

    fixes: list[Fix] = []
    if not blockers:
        fixes.append(
            _set_fix(
                node.path, "rfc_state", target_state.value, f"set rfc_state: {target_state.value}"
            )
        )
        if fm.status != StatusEnum.stable:
            fixes.append(
                _set_fix(node.path, "status", StatusEnum.stable.value, "set status: stable")
            )
        if target_state == RfcStateEnum.accepted:
            if resolved_by and resolved_by != fm.resolved_by:
                fixes.append(
                    _set_fix(
                        node.path, "resolved_by", resolved_by, f"set resolved_by: {resolved_by}"
                    )
                )
            if fm.required_updates is None:
                fixes.append(
                    _set_fix(
                        node.path,
                        "required_updates",
                        [],
                        "add required_updates: [] (list downstream docs if any)",
                    )
                )
        section = _TARGET_SECTIONS[target_state]
        headings = graph.headings.get(node.id, [])
        from irminsul.docgraph_index import slugify

        has_terminal_section = _has_heading(headings, slugify(section)) or _has_heading(
            headings, "resolution"
        )
        if not has_terminal_section:
            fixes.append(
                Fix(
                    path=node.path,
                    description=f"insert '## {section}' stub in {rfc_path}",
                    apply=_section_appender(section),
                    requires_confirm=True,
                )
            )

    return TransitionPlan(
        change=node.id,
        path=node.path,
        current_state=fm.rfc_state.value,
        target_state=target_state.value,
        blockers=tuple(blockers),
        fixes=tuple(fixes),
        notes=tuple(notes),
    )


def _set_fix(path: Path, key: str, value: object, description: str) -> Fix:
    def apply(text: str) -> str:
        return set_value(text, key, value)

    return Fix(
        path=path,
        description=f"{description} in {path.as_posix()}",
        apply=apply,
        requires_confirm=True,
    )


def _section_appender(title: str) -> Callable[[str], str]:
    def apply(text: str) -> str:
        return _append_section(text, title)

    return apply
