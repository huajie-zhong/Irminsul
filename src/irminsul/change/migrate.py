"""Inventory and explicitly classify RFCs created before structured lifecycle state."""

from __future__ import annotations

import json
import posixpath
from collections.abc import Callable
from dataclasses import asdict, dataclass
from pathlib import Path

from irminsul.change.report import (
    Blocker,
    ChangeError,
    find_rfc_artifact,
    requirement_blockers,
)
from irminsul.checks.base import Fix
from irminsul.config import IrminsulConfig, docs_root_prefix
from irminsul.docgraph import DocGraph, DocNode
from irminsul.frontmatter import (
    AudienceEnum,
    RequiredUpdateEntry,
    RequiredUpdateKindEnum,
    RfcStateEnum,
    StatusEnum,
)
from irminsul.frontmatter_edit import set_value
from irminsul.rfc_freeze import seal_text

MIGRATION_VERSION = 1
MigrationUpdate = RequiredUpdateEntry | dict[str, str]


@dataclass(frozen=True)
class MigrationCandidate:
    id: str
    path: str
    title: str
    status: str
    affects: tuple[str, ...] | None
    resolved_by: str | None
    required_updates: tuple[str, ...] | None
    decision_links: tuple[str, ...]
    implementation_backlinks: tuple[str, ...]
    headings: tuple[str, ...]
    recommended_state: None = None


@dataclass(frozen=True)
class MigrationPlan:
    version: int
    candidate: MigrationCandidate
    target_state: str
    blockers: tuple[Blocker, ...]
    changes: tuple[str, ...]
    fix: Fix | None


def inventory_candidates(graph: DocGraph, config: IrminsulConfig) -> list[MigrationCandidate]:
    prefix = f"{docs_root_prefix(config)}/80-evolution/rfcs/"
    nodes = [
        node
        for node in graph.nodes.values()
        if node.path.as_posix().startswith(prefix)
        and node.path.name != "INDEX.md"
        and node.frontmatter.rfc_state is None
    ]
    return [_candidate(graph, node) for node in sorted(nodes, key=lambda item: item.id)]


def get_candidate(
    graph: DocGraph,
    config: IrminsulConfig,
    change: str,
) -> tuple[DocNode, MigrationCandidate]:
    node = find_rfc_artifact(graph, config, change)
    if node.path.name == "INDEX.md" or node.frontmatter.rfc_state is not None:
        raise ChangeError(f"'{node.id}' is not a pre-lifecycle migration candidate", code=2)
    return node, _candidate(graph, node)


def _candidate(graph: DocGraph, node: DocNode) -> MigrationCandidate:
    weak = graph.inbound_weak.get(node.id, set())
    decision_links = sorted(
        graph.nodes[source].path.as_posix()
        for source in weak
        if source in graph.nodes and graph.nodes[source].frontmatter.audience == AudienceEnum.adr
    )
    implementation_backlinks = sorted(
        candidate.path.as_posix()
        for candidate in graph.nodes.values()
        if node.id in candidate.frontmatter.implements
    )
    required_updates = node.frontmatter.required_updates
    return MigrationCandidate(
        id=node.id,
        path=node.path.as_posix(),
        title=node.frontmatter.title,
        status=node.frontmatter.status.value,
        affects=(tuple(node.frontmatter.affects) if node.frontmatter.affects is not None else None),
        resolved_by=node.frontmatter.resolved_by,
        required_updates=(
            tuple(update.path for update in required_updates)
            if required_updates is not None
            else None
        ),
        decision_links=tuple(decision_links),
        implementation_backlinks=tuple(implementation_backlinks),
        headings=tuple(heading.text for heading in graph.headings.get(node.id, [])),
    )


def plan_migration(
    graph: DocGraph,
    config: IrminsulConfig,
    change: str,
    state: str,
    *,
    resolved_by: str | None = None,
    affects: list[str] | None = None,
    affects_none: bool = False,
    required_updates: list[str] | None = None,
    no_required_updates: bool = False,
    reason: str | None = None,
    attest_implemented: bool = False,
) -> MigrationPlan:
    node, candidate = get_candidate(graph, config, change)
    try:
        target = RfcStateEnum(state)
    except ValueError:
        raise ChangeError(
            f"unknown migration state '{state}'; expected draft, accepted, implemented, or rejected",
            code=2,
        ) from None
    if target not in {
        RfcStateEnum.draft,
        RfcStateEnum.accepted,
        RfcStateEnum.implemented,
        RfcStateEnum.rejected,
    }:
        raise ChangeError(f"deprecated state '{state}' is not a migration target", code=2)

    affects = _unique(affects or [])
    required_updates = _unique(required_updates or [])
    reason = reason.strip() if reason is not None else None
    _validate_option_shape(
        target,
        affects,
        affects_none,
        required_updates,
        no_required_updates,
        resolved_by,
        reason,
        attest_implemented,
    )

    blockers: list[Blocker] = []
    fm = node.frontmatter
    path = node.path.as_posix()
    if fm.lifecycle_migration is not None:
        blockers.append(
            Blocker(
                code="existing-migration-provenance",
                message="RFC already carries lifecycle_migration metadata without rfc_state",
                path=path,
                suggestion="repair the partial migration manually before retrying",
            )
        )
    if fm.frozen_hash is not None and target != RfcStateEnum.implemented:
        blockers.append(
            Blocker(
                code="premature-frozen-hash",
                message="only an implemented migration may retain and recompute a frozen hash",
                path=path,
                suggestion="remove the premature seal or choose implemented with attestation",
            )
        )

    effective_affects = _effective_affects(fm.affects, affects, affects_none)
    effective_updates = _effective_required_updates(
        fm.required_updates,
        required_updates,
        no_required_updates,
    )
    effective_resolved_by = fm.resolved_by or resolved_by

    terminal = target in {RfcStateEnum.accepted, RfcStateEnum.implemented}
    if terminal:
        if effective_affects is None:
            blockers.append(
                Blocker(
                    code="missing-affects-decision",
                    message="accepted and implemented migrations need explicit affected scope",
                    path=path,
                    suggestion="pass --affects <component> or --affects-none",
                )
            )
        else:
            for component in effective_affects:
                if component not in graph.nodes:
                    blockers.append(
                        Blocker(
                            code="unknown-component",
                            message=f"affected component '{component}' does not resolve",
                            path=path,
                        )
                    )
        if effective_updates is None:
            blockers.append(
                Blocker(
                    code="missing-required-updates-decision",
                    message="accepted and implemented migrations need an explicit update disposition",
                    path=path,
                    suggestion="pass --required-update <path> or --no-required-updates",
                )
            )
        else:
            blockers.extend(_required_update_blockers(graph, node, effective_updates))
        blockers.extend(
            _decision_blockers(graph, node, effective_resolved_by, resolved_by, fm.resolved_by)
        )

    if target == RfcStateEnum.accepted:
        blockers.extend(requirement_blockers(graph, node))
    if target == RfcStateEnum.implemented and not attest_implemented:
        blockers.append(
            Blocker(
                code="missing-implementation-attestation",
                message="historical implemented migration requires --attest-implemented",
                path=path,
                suggestion="obtain human approval and re-run with --attest-implemented",
            )
        )

    changes = _planned_changes(
        node,
        target,
        effective_resolved_by,
        effective_affects,
        effective_updates,
        reason,
    )
    fix = None
    if not blockers:
        fix = Fix(
            path=node.path,
            description=f"migrate {node.id} to {target.value}",
            apply=_migration_transform(
                node,
                target,
                effective_resolved_by,
                effective_affects,
                effective_updates,
                reason,
            ),
            requires_confirm=True,
        )
    return MigrationPlan(
        version=MIGRATION_VERSION,
        candidate=candidate,
        target_state=target.value,
        blockers=tuple(blockers),
        changes=tuple(changes),
        fix=fix,
    )


def _validate_option_shape(
    target: RfcStateEnum,
    affects: list[str],
    affects_none: bool,
    required_updates: list[str],
    no_required_updates: bool,
    resolved_by: str | None,
    reason: str | None,
    attest_implemented: bool,
) -> None:
    if affects and affects_none:
        raise ChangeError("--affects and --affects-none are mutually exclusive", code=2)
    if required_updates and no_required_updates:
        raise ChangeError(
            "--required-update and --no-required-updates are mutually exclusive", code=2
        )
    terminal = target in {RfcStateEnum.accepted, RfcStateEnum.implemented}
    if not terminal and (affects or affects_none or required_updates or no_required_updates):
        raise ChangeError(
            "scope and required-update flags apply only to accepted/implemented", code=2
        )
    if not terminal and resolved_by is not None:
        raise ChangeError("--resolved-by applies only to accepted/implemented", code=2)
    if target == RfcStateEnum.rejected:
        if not reason:
            raise ChangeError("rejected migration requires --reason", code=2)
    elif reason is not None:
        raise ChangeError("--reason applies only to rejected migration", code=2)
    if target != RfcStateEnum.implemented and attest_implemented:
        raise ChangeError("--attest-implemented applies only to implemented migration", code=2)


def _effective_affects(
    existing: list[str] | None,
    supplied: list[str],
    supplied_none: bool,
) -> list[str] | None:
    if existing is not None:
        if supplied or supplied_none:
            raise ChangeError("RFC already declares affects; do not pass scope flags", code=2)
        return list(existing)
    if supplied_none:
        return []
    return supplied or None


def _effective_required_updates(
    existing: list[RequiredUpdateEntry] | None,
    supplied: list[str],
    supplied_none: bool,
) -> list[MigrationUpdate] | None:
    if existing is not None:
        if supplied or supplied_none:
            raise ChangeError(
                "RFC already declares required_updates; do not pass update flags", code=2
            )
        return list(existing)
    if supplied_none:
        return []
    if supplied:
        return [
            {"path": path, "reason": "Declared during lifecycle migration", "kind": "update"}
            for path in supplied
        ]
    return None


def _decision_blockers(
    graph: DocGraph,
    node: DocNode,
    effective: str | None,
    supplied: str | None,
    existing: str | None,
) -> list[Blocker]:
    path = node.path.as_posix()
    if existing is not None and supplied is not None and supplied != existing:
        raise ChangeError("RFC already declares a different resolved_by path", code=2)
    if effective is None:
        return [
            Blocker(
                code="missing-decision",
                message="accepted and implemented migrations require a resolving ADR",
                path=path,
                suggestion="pass --resolved-by <repo-relative ADR path>",
            )
        ]
    target = graph.by_path.get(Path(effective.replace("\\", "/")))
    if target is None:
        return [
            Blocker(
                code="missing-decision",
                message=f"resolved_by '{effective}' does not resolve",
                path=path,
            )
        ]
    out: list[Blocker] = []
    if (
        target.frontmatter.audience != AudienceEnum.adr
        or target.frontmatter.status != StatusEnum.stable
    ):
        out.append(
            Blocker(
                code="invalid-decision-owner",
                message=f"resolved_by '{effective}' is not a stable ADR",
                path=target.path.as_posix(),
            )
        )
    if target.id not in graph.inbound_weak.get(node.id, set()):
        out.append(
            Blocker(
                code="missing-decision-backlink",
                message=f"decision '{effective}' does not link back to RFC '{node.id}'",
                path=target.path.as_posix(),
                suggestion="add a Markdown link to the RFC in the human-approved decision",
            )
        )
    return out


def _required_update_blockers(
    graph: DocGraph,
    node: DocNode,
    updates: list[MigrationUpdate],
) -> list[Blocker]:
    out: list[Blocker] = []
    for update in updates:
        update_path = update["path"] if isinstance(update, dict) else update.path
        kind = update.get("kind", "update") if isinstance(update, dict) else update.kind
        kind_value = kind.value if isinstance(kind, RequiredUpdateKindEnum) else str(kind)
        normalized = Path(str(update_path).replace("\\", "/"))
        if normalized.is_absolute():
            out.append(
                Blocker(
                    code="absolute-required-update",
                    message=f"required update '{update_path}' must be repo-relative",
                    path=node.path.as_posix(),
                )
            )
        elif kind_value != RequiredUpdateKindEnum.create.value and normalized not in graph.by_path:
            out.append(
                Blocker(
                    code="missing-required-update",
                    message=f"required update '{update_path}' does not resolve to a doc atom",
                    path=node.path.as_posix(),
                )
            )
    return out


def _planned_changes(
    node: DocNode,
    target: RfcStateEnum,
    resolved_by: str | None,
    affects: list[str] | None,
    required_updates: list[MigrationUpdate] | None,
    reason: str | None,
) -> list[str]:
    changes = [
        f"set rfc_state: {target.value}",
        "record lifecycle_migration provenance",
    ]
    if target != RfcStateEnum.draft and node.frontmatter.status != StatusEnum.stable:
        changes.append("set status: stable")
    if resolved_by is not None:
        changes.append(f"set resolved_by: {resolved_by}")
    if affects is not None:
        changes.append(f"set affects: {affects}")
    if required_updates is not None:
        changes.append(f"set required_updates ({len(required_updates)} entries)")
    if target == RfcStateEnum.rejected:
        changes.append(f"append rejection rationale: {reason}")
    elif target in {RfcStateEnum.accepted, RfcStateEnum.implemented}:
        changes.append("append resolution section if missing")
    if target == RfcStateEnum.implemented:
        changes.append("seal migrated RFC last")
    return changes


def _migration_transform(
    node: DocNode,
    target: RfcStateEnum,
    resolved_by: str | None,
    affects: list[str] | None,
    required_updates: list[MigrationUpdate] | None,
    reason: str | None,
) -> Callable[[str], str]:
    basis = (
        "human-implementation-attestation"
        if target == RfcStateEnum.implemented
        else "human-classification"
    )

    def apply(text: str) -> str:
        updated = set_value(text, "rfc_state", target.value)
        if target != RfcStateEnum.draft:
            updated = set_value(updated, "status", StatusEnum.stable.value)
        if resolved_by is not None:
            updated = set_value(updated, "resolved_by", resolved_by)
        if affects is not None:
            updated = set_value(updated, "affects", affects)
        if required_updates is not None:
            normalized_updates = [
                update if isinstance(update, dict) else update.model_dump(mode="json")
                for update in required_updates
            ]
            updated = set_value(updated, "required_updates", normalized_updates)
        updated = set_value(
            updated,
            "lifecycle_migration",
            {"source": "pre-lifecycle", "basis": basis},
        )
        if target == RfcStateEnum.rejected:
            updated = _append_terminal_section(updated, "Rejection Rationale", reason or "")
        elif target in {RfcStateEnum.accepted, RfcStateEnum.implemented}:
            relative = posixpath.relpath(
                resolved_by or "",
                node.path.parent.as_posix(),
            )
            body = (
                "Lifecycle state was classified during pre-lifecycle migration. "
                f"See [`{Path(resolved_by or '').stem}`]({relative})."
            )
            updated = _append_terminal_section(updated, "Resolution", body)
        if target == RfcStateEnum.implemented:
            updated = seal_text(updated)
        return updated

    return apply


def _append_terminal_section(text: str, title: str, body: str) -> str:
    heading = f"## {title}"
    if any(line.strip().casefold() == heading.casefold() for line in text.splitlines()):
        return text
    return f"{text.rstrip()}\n\n{heading}\n\n{body.strip()}\n"


def _unique(values: list[str]) -> list[str]:
    return list(dict.fromkeys(value.strip() for value in values if value.strip()))


def inventory_to_json(candidates: list[MigrationCandidate]) -> str:
    return json.dumps(
        {
            "version": MIGRATION_VERSION,
            "state_inference": False,
            "candidates": [asdict(candidate) for candidate in candidates],
        },
        indent=2,
    )


def format_inventory_plain(candidates: list[MigrationCandidate]) -> str:
    if not candidates:
        return "pre-lifecycle RFCs: (none)"
    lines = [f"pre-lifecycle RFCs: {len(candidates)}", "  state inference: disabled"]
    for candidate in candidates:
        lines.append(
            f"  {candidate.id} [{candidate.status}] {candidate.path} "
            f"(decisions: {len(candidate.decision_links)}, implementations: "
            f"{len(candidate.implementation_backlinks)})"
        )
    lines.append("  inspect: irminsul change migrate <id> --format json")
    return "\n".join(lines)


def plan_to_json(
    plan: MigrationPlan,
    *,
    applied: bool = False,
    written: bool = False,
) -> str:
    return json.dumps(
        {
            "version": plan.version,
            "candidate": asdict(plan.candidate),
            "target_state": plan.target_state,
            "blockers": [asdict(blocker) for blocker in plan.blockers],
            "changes": list(plan.changes),
            "will_write": plan.fix is not None,
            "applied": applied,
            "written": written,
        },
        indent=2,
    )


def format_plan_plain(plan: MigrationPlan) -> str:
    lines = [f"{plan.candidate.id}: pre-lifecycle -> {plan.target_state}"]
    if plan.blockers:
        lines.append("  blockers:")
        for blocker in plan.blockers:
            lines.append(f"    [{blocker.code}] {blocker.message}")
    else:
        lines.append("  planned changes:")
        lines.extend(f"    - {change}" for change in plan.changes)
    return "\n".join(lines)
