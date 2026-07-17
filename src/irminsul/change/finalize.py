"""`change finalize` (RFC 0032): the only transition from accepted to implemented.

Finalization verifies mechanical preconditions, accepts explicitly confirmed
requirement-to-symbol bindings (`--anchor req=path#symbol`), promotes
code-backed requirements into the owning component docs as anchored claims,
and flips `rfc_state: implemented` only after every component-doc write
succeeded. The anchor is a persistent freshness tripwire, not proof of
behavior — tests, agents, and humans still judge semantic satisfaction.
"""

from __future__ import annotations

import os
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from pathlib import Path

from irminsul.anchors import Anchor, resolve
from irminsul.change.footprint import most_specific_claims, touched_components
from irminsul.change.report import (
    Blocker,
    ChangeError,
    _hard_errors,
    find_rfc_node,
    requirement_blockers,
    resolve_change_baseline,
)
from irminsul.checks.base import Fix
from irminsul.checks.decision_updates import DecisionUpdatesCheck
from irminsul.checks.globs import walk_configured_source_files
from irminsul.checks.uniqueness import resolve_claims
from irminsul.config import IrminsulConfig
from irminsul.docgraph import DocGraph, DocNode
from irminsul.docgraph_index import Requirement
from irminsul.frontmatter import RfcStateEnum, StatusEnum, canonical_rfc_state
from irminsul.frontmatter_edit import add_to_list, set_value
from irminsul.rfc_freeze import seal_text

PROMOTED_SECTION = "Implemented requirements"


@dataclass(frozen=True)
class Promotion:
    """One requirement promoted into one owning component doc."""

    global_id: str  # <rfc-id>#<requirement-id>
    owner: str  # component doc id
    owner_path: Path
    text: str
    provenance: str
    anchors: tuple[str, ...]  # "path#symbol @sha256:hash" marker payloads
    already_promoted: bool
    implements_present: bool


@dataclass(frozen=True)
class FinalizePlan:
    change: str
    path: Path
    current_state: str
    blockers: tuple[Blocker, ...]
    promotions: tuple[Promotion, ...]
    component_fixes: tuple[Fix, ...]
    rfc_fixes: tuple[Fix, ...]
    notes: tuple[str, ...] = ()


def parse_binding_flags(values: list[str], flag: str) -> dict[str, list[str]]:
    """Parse repeated `req-id=value` flags into an ordered mapping."""
    out: dict[str, list[str]] = {}
    for raw in values:
        req_id, sep, value = raw.partition("=")
        if not sep or not req_id.strip() or not value.strip():
            raise ChangeError(
                f"malformed {flag} '{raw}'; expected <requirement-id>=<value>", code=2
            )
        out.setdefault(req_id.strip(), []).append(value.strip())
    return out


def plan_finalize(
    graph: DocGraph,
    config: IrminsulConfig,
    repo_root: Path,
    change: str,
    *,
    bindings: dict[str, list[str]] | None = None,
    owners: dict[str, list[str]] | None = None,
    base_ref: str | None = None,
    env: Mapping[str, str] | None = None,
) -> FinalizePlan:
    bindings = bindings or {}
    owners = owners or {}
    node = find_rfc_node(graph, config, change)
    fm = node.frontmatter
    assert fm.rfc_state is not None
    canonical = canonical_rfc_state(fm.rfc_state)
    rfc_path = node.path.as_posix()

    blockers: list[Blocker] = []
    notes: list[str] = []

    already_implemented = canonical == RfcStateEnum.implemented
    if not already_implemented and canonical != RfcStateEnum.accepted:
        blockers.append(
            Blocker(
                code="invalid-state",
                message=(f"only an accepted RFC can be finalized; this one is {canonical.value}"),
                path=rfc_path,
                suggestion="run `irminsul change transition <id> accepted --confirm` first",
            )
        )

    if fm.resolved_by is None or graph.by_path.get(Path(fm.resolved_by.replace("\\", "/"))) is None:
        blockers.append(
            Blocker(
                code="unresolved-adr",
                message="the RFC must resolve to an existing decision record",
                path=rfc_path,
            )
        )

    if not any(h.slug == "resolution" for h in graph.headings.get(node.id, [])):
        blockers.append(
            Blocker(
                code="missing-resolution-section",
                message="an implemented RFC needs a '## Resolution' section",
                path=rfc_path,
                suggestion="record the outcome and link the decision doc",
            )
        )

    if fm.affects is None:
        blockers.append(
            Blocker(
                code="missing-affects",
                message="finalization needs explicit `affects` (use [] for no owned source)",
                path=rfc_path,
            )
        )

    blockers.extend(requirement_blockers(graph, node))

    baseline = resolve_change_baseline(repo_root, base_ref, env=env)
    if baseline.changed_paths is None:
        blockers.append(
            Blocker(
                code="unknown-baseline",
                message="no diff baseline could be resolved; finalization cannot verify scope",
                path=rfc_path,
                suggestion="pass --base-ref <ref> covering the implementation range",
            )
        )
    else:
        footprint = touched_components(graph, config, frozenset(baseline.changed_paths))
        declared = set(fm.affects or [])
        undeclared = sorted(set(footprint.touched) - declared)
        if undeclared:
            blockers.append(
                Blocker(
                    code="unreconciled-scope",
                    message=(
                        "touched-but-undeclared component(s) must be reconciled before "
                        f"finalization: {', '.join(undeclared)}"
                    ),
                    path=rfc_path,
                    suggestion="update `affects` or record a reviewed exception in the RFC",
                )
            )
        for unowned in footprint.unowned_source:
            blockers.append(
                Blocker(
                    code="unowned-change",
                    message=f"changed source '{unowned}' has no component claim",
                    path=unowned,
                    suggestion="extend a component doc's `describes` (curated, not automatic)",
                )
            )

    for finding in _hard_errors(graph, config):
        blockers.append(
            Blocker(
                code=f"hard-check:{finding.check}",
                message=finding.message,
                path=finding.path.as_posix() if finding.path else None,
                suggestion=finding.suggestion,
            )
        )

    promotions: list[Promotion] = []
    section = graph.requirements.get(node.id)
    if section is not None and section.disposition is None:
        promotions, promotion_blockers = _plan_promotions(
            graph, config, repo_root, node, section.requirements, bindings, owners
        )
        blockers.extend(promotion_blockers)

    declared_req_ids = {
        req.req_id for req in (section.requirements if section else ()) if req.req_id
    }
    for flag, supplied in (("--anchor", bindings), ("--owner", owners)):
        for req_id in sorted(set(supplied) - declared_req_ids):
            blockers.append(
                Blocker(
                    code="unknown-requirement",
                    message=(
                        f"{flag} names requirement '{req_id}' which this RFC does not declare"
                    ),
                    path=rfc_path,
                )
            )

    blockers.extend(_decision_update_blockers(graph, node, {p.owner for p in promotions}))

    component_fixes: list[Fix] = []
    rfc_fixes: list[Fix] = []
    if not blockers:
        backlinked: set[str] = set()
        for promotion in promotions:
            if promotion.already_promoted:
                notes.append(
                    f"claim {promotion.global_id} already present in "
                    f"{promotion.owner_path.as_posix()}; skipping the claim entry"
                )
            else:
                component_fixes.append(_promotion_fix(node, promotion))
            if promotion.implements_present or promotion.owner in backlinked:
                continue
            backlinked.add(promotion.owner)
            component_fixes.append(
                Fix(
                    path=promotion.owner_path,
                    description=(f"add implements: {node.id} to {promotion.owner_path.as_posix()}"),
                    apply=_implements_adder(node.id),
                    requires_confirm=True,
                )
            )
        if not already_implemented:
            rfc_fixes.append(
                Fix(
                    path=node.path,
                    description=f"set rfc_state: implemented in {rfc_path}",
                    apply=_value_setter("rfc_state", RfcStateEnum.implemented.value),
                    requires_confirm=True,
                )
            )
            if fm.status != StatusEnum.stable:
                rfc_fixes.append(
                    Fix(
                        path=node.path,
                        description=f"set status: stable in {rfc_path}",
                        apply=_value_setter("status", StatusEnum.stable.value),
                        requires_confirm=True,
                    )
                )
        if fm.frozen_hash is None:
            rfc_fixes.append(
                Fix(
                    path=node.path,
                    description=f"freeze implemented RFC in {rfc_path}",
                    apply=seal_text,
                    requires_confirm=True,
                )
            )
        if already_implemented and not component_fixes and not rfc_fixes:
            notes.append("RFC is already implemented and every claim is promoted; nothing to do")

    return FinalizePlan(
        change=node.id,
        path=node.path,
        current_state=fm.rfc_state.value,
        blockers=tuple(blockers),
        promotions=tuple(promotions),
        component_fixes=tuple(component_fixes),
        rfc_fixes=tuple(rfc_fixes),
        notes=tuple(notes),
    )


def _decision_update_blockers(
    graph: DocGraph, node: DocNode, promotion_owners: set[str]
) -> list[Blocker]:
    """Required-update blockers for this RFC.

    A `missing-backlink` against a doc this run will promote into is not a
    blocker: adding that `implements` entry is exactly what finalization does,
    and blocking on it would make the write that resolves it unreachable.
    """
    out: list[Blocker] = []
    for finding in DecisionUpdatesCheck().run(graph):
        relates = finding.doc_id == node.id or f"'{node.id}'" in finding.message
        if not relates or finding.category not in (
            "no-required-updates-field",
            "missing-required-update-path",
            "missing-backlink",
        ):
            continue
        if finding.category == "missing-backlink" and finding.doc_id in promotion_owners:
            continue
        out.append(
            Blocker(
                code=f"decision-updates:{finding.category}",
                message=finding.message,
                path=finding.path.as_posix() if finding.path else None,
                suggestion=finding.suggestion,
            )
        )
    return out


def _plan_promotions(
    graph: DocGraph,
    config: IrminsulConfig,
    repo_root: Path,
    node: DocNode,
    requirements: tuple[Requirement, ...],
    bindings: dict[str, list[str]],
    owners: dict[str, list[str]],
) -> tuple[list[Promotion], list[Blocker]]:
    blockers: list[Blocker] = []
    promotions: list[Promotion] = []
    rfc_path = node.path.as_posix()
    declared = list(node.frontmatter.affects or [])

    source_files = walk_configured_source_files(repo_root, config).files
    display_index = {display: (abs_path, display) for abs_path, display in source_files}

    for req in requirements:
        if req.req_id is None:
            continue  # grammar blockers already cover this
        global_id = f"{node.id}#{req.req_id}"
        req_bindings = bindings.get(req.req_id, [])
        owner_choices = owners.get(req.req_id, [])

        marker_payloads: list[str] = []
        binding_owner_candidates: set[str] = set()

        if req.provenance == "code":
            if not req_bindings:
                blockers.append(
                    Blocker(
                        code="missing-binding",
                        message=(
                            f"code-provenance requirement '{req.req_id}' has no confirmed binding"
                        ),
                        path=rfc_path,
                        suggestion=(
                            f"pass --anchor {req.req_id}=<path>#<symbol> for the code "
                            "and test evidence you reviewed"
                        ),
                    )
                )
                continue
            for binding in req_bindings:
                raw_path, _, symbol_part = binding.partition("#")
                # POSIX-normalize before resolving: a Windows-authored
                # `app\auth\login.py` must persist (and re-resolve in CI) as
                # `app/auth/login.py`.
                path_part = raw_path.replace("\\", "/")
                target = f"{path_part}#{symbol_part}" if symbol_part else path_part
                anchor = Anchor(
                    line=0,
                    raw=target,
                    path=path_part,
                    symbol=symbol_part or None,
                    pinned=None,
                )
                resolution = resolve(repo_root, anchor)
                if resolution.status != "ok" or resolution.current is None:
                    blockers.append(
                        Blocker(
                            code="unresolvable-binding",
                            message=(
                                f"binding '{target}' for requirement '{req.req_id}' "
                                f"did not resolve ({resolution.status})"
                            ),
                            path=path_part,
                        )
                    )
                    continue
                marker_payloads.append(f"{target} @sha256:{resolution.current}")
                claims = resolve_claims(
                    graph, [display_index[path_part]] if path_part in display_index else []
                )
                for claim_node in most_specific_claims(claims.get(path_part, [])):
                    if claim_node.id in declared:
                        binding_owner_candidates.add(claim_node.id)
        elif req_bindings:
            blockers.append(
                Blocker(
                    code="unsupported-binding",
                    message=(
                        f"--anchor was given for requirement '{req.req_id}' whose provenance is "
                        f"'{req.provenance or 'unspecified'}'; only code-provenance requirements "
                        "take confirmed anchors"
                    ),
                    path=rfc_path,
                    suggestion=(
                        "drop the --anchor, or declare `Provenance: code` on the requirement"
                    ),
                )
            )
            continue

        owner = _choose_owner(
            req.req_id,
            owner_choices,
            sorted(binding_owner_candidates),
            declared,
            blockers,
            rfc_path,
        )
        if owner is None:
            continue
        owner_node = graph.nodes.get(owner)
        if owner_node is None:
            continue  # unknown-component blockers already cover this

        promotions.append(
            Promotion(
                global_id=global_id,
                owner=owner,
                owner_path=owner_node.path,
                text=_first_paragraph(req.text) or req.title,
                provenance=req.provenance or "code",
                anchors=tuple(marker_payloads),
                already_promoted=f"**{global_id}**" in owner_node.body,
                implements_present=node.id in owner_node.frontmatter.implements,
            )
        )

    return promotions, blockers


def _choose_owner(
    req_id: str,
    owner_choices: list[str],
    candidates: list[str],
    declared: list[str],
    blockers: list[Blocker],
    rfc_path: str,
) -> str | None:
    if owner_choices:
        distinct = sorted(set(owner_choices))
        if len(distinct) > 1:
            blockers.append(
                Blocker(
                    code="conflicting-owner",
                    message=(
                        f"conflicting --owner values for requirement '{req_id}': "
                        f"{', '.join(distinct)}"
                    ),
                    path=rfc_path,
                    suggestion="pass exactly one owner per requirement",
                )
            )
            return None
        choice = distinct[0]
        if choice not in declared:
            blockers.append(
                Blocker(
                    code="owner-not-declared",
                    message=(
                        f"--owner for requirement '{req_id}' names '{choice}' which is "
                        "not in `affects`"
                    ),
                    path=rfc_path,
                )
            )
            return None
        return choice
    if len(candidates) == 1:
        return candidates[0]
    if not candidates and len(declared) == 1:
        return declared[0]
    if not declared:
        blockers.append(
            Blocker(
                code="no-owner",
                message=(f"requirement '{req_id}' has no candidate owner: `affects` is empty"),
                path=rfc_path,
                suggestion="declare the owning component in `affects`",
            )
        )
        return None
    blockers.append(
        Blocker(
            code="ambiguous-owner",
            message=(
                f"requirement '{req_id}' has "
                f"{'multiple' if candidates else 'no'} plausible owner(s)"
                f"{': ' + ', '.join(candidates) if candidates else ''}; "
                "an explicit choice is required"
            ),
            path=rfc_path,
            suggestion=f"pass --owner {req_id}=<component id>",
        )
    )
    return None


def _first_paragraph(text: str) -> str:
    for chunk in text.split("\n\n"):
        cleaned = " ".join(line.strip() for line in chunk.splitlines()).strip()
        if cleaned:
            return cleaned
    return ""


def _rfc_link(owner_path: Path, rfc_path: Path) -> str:
    return os.path.relpath(rfc_path, owner_path.parent).replace("\\", "/")


def _promotion_fix(node: DocNode, promotion: Promotion) -> Fix:
    link = _rfc_link(promotion.owner_path, node.path)
    entry_lines = [
        f"- **{promotion.global_id}** — {promotion.text} "
        f"(provenance: {promotion.provenance}; [RFC]({link}))"
    ]
    entry_lines.extend(f"  <!-- anchor: {payload} -->" for payload in promotion.anchors)
    entry = "\n".join(entry_lines)

    def apply(text: str) -> str:
        if f"**{promotion.global_id}**" in text:
            return text
        heading = f"## {PROMOTED_SECTION}"
        idx = text.find(heading)
        if idx == -1:
            sep = "" if text.endswith("\n\n") else ("\n" if text.endswith("\n") else "\n\n")
            return f"{text}{sep}{heading}\n\n{entry}\n"
        # Append the entry at the end of the existing section.
        next_h2 = text.find("\n## ", idx + len(heading))
        if next_h2 == -1:
            return f"{text.rstrip()}\n{entry}\n"
        return f"{text[:next_h2].rstrip()}\n{entry}\n{text[next_h2:]}"

    return Fix(
        path=promotion.owner_path,
        description=(f"promote {promotion.global_id} into {promotion.owner_path.as_posix()}"),
        apply=apply,
        requires_confirm=True,
    )


def _implements_adder(rfc_id: str) -> Callable[[str], str]:
    def apply(text: str) -> str:
        return add_to_list(text, "implements", rfc_id)

    return apply


def _value_setter(key: str, value: str) -> Callable[[str], str]:
    def apply(text: str) -> str:
        return set_value(text, key, value)

    return apply
