"""`change finalize`: the only transition from accepted to implemented.

Finalization verifies mechanical preconditions, accepts explicitly confirmed
requirement-to-symbol bindings (`--anchor req=path#symbol`), promotes
code-backed requirements into the owning component docs as anchored claims,
and flips `rfc_state: implemented` only after every component-doc write
succeeded. The anchor is a persistent freshness tripwire, not proof of
behavior — tests, agents, and humans still judge semantic satisfaction.

A requirement that names what its RFC removes names phrases the resolving decision record
tombstones, and `retired-references` would report the claim it becomes. So the promoted
text links each such mention to that record, the citation that check accepts, and a claim
line the check would still report is a `promoted-retired-reference` blocker rather than a
doc `check` fails.
"""

from __future__ import annotations

import os
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

from irminsul.anchors import Anchor, resolve
from irminsul.change.gate import Issue
from irminsul.change.report import ChangeError, ChangeReport, build_change_report
from irminsul.checks.base import Fix
from irminsul.checks.retired_references import (
    RetirementRule,
    link_retired_mentions,
    reported_retirements,
    retirement_registry,
)
from irminsul.checks.rfc_follow_through import (
    RfcFollowThroughCheck,
    implements_fix,
    stable_status_fixes,
)
from irminsul.checks.uniqueness import most_specific_claims
from irminsul.config import IrminsulConfig
from irminsul.docgraph import DocGraph, DocNode
from irminsul.docgraph_index import Requirement, global_requirement_id
from irminsul.frontmatter import RfcStateEnum
from irminsul.frontmatter_edit import setter
from irminsul.git.changes import GitChangesError, working_tree_changed_paths
from irminsul.git.reader import GitReader

PROMOTED_SECTION = "Implemented requirements"
_MAX_NAMED_PATHS = 5


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
    blockers: tuple[Issue, ...]
    promotions: tuple[Promotion, ...]
    component_fixes: tuple[Fix, ...]
    rfc_fixes: tuple[Fix, ...]
    report: ChangeReport
    """`change verify`'s report for `implemented`, whose blockers this plan starts from."""
    notes: tuple[str, ...] = ()


def refuse_uncommitted_work(git: GitReader, repo_root: Path) -> None:
    """Raise `ChangeError` naming the paths when the working tree is not clean.

    Finalization writes to the tree and verifies the change it will be committed with, and
    work that is not committed yet is a change that does not exist. A tree git cannot read
    is left to the plan, whose baseline blocker says so.
    """
    try:
        dirty = working_tree_changed_paths(git, repo_root)
    except GitChangesError:
        return
    if not dirty:
        return
    named = ", ".join(dirty[:_MAX_NAMED_PATHS])
    if len(dirty) > _MAX_NAMED_PATHS:
        named += f" and {len(dirty) - _MAX_NAMED_PATHS} more"
    raise ChangeError(
        f"change finalize needs a clean working tree; {len(dirty)} path(s) are not committed: "
        f"{named}. Commit or stash first.",
        code=1,
    )


def parse_binding_flags(values: list[str], flag: str) -> dict[str, list[str]]:
    """Parse repeated `req-id=value` flags into an ordered mapping."""
    out: dict[str, list[str]] = {}
    for raw in values:
        req_id, sep, value = raw.partition("=")
        if not sep or not req_id.strip() or not value.strip():
            raise ChangeError(f"malformed {flag} '{raw}'; expected <requirement-id>=<value>")
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
    report = build_change_report(
        repo_root,
        config,
        change,
        base_ref=base_ref,
        env=env,
        graph=graph,
        target=RfcStateEnum.implemented,
    )
    node = graph.nodes[report.change]
    fm = node.frontmatter
    assert fm.rfc_state is not None
    rfc_path = node.path.as_posix()

    blockers: list[Issue] = []
    notes: list[str] = []

    already_implemented = fm.rfc_state == RfcStateEnum.implemented
    if not already_implemented and fm.rfc_state != RfcStateEnum.accepted:
        blockers.append(
            Issue(
                code="invalid-state",
                message=(
                    f"only an accepted RFC can be finalized; this one is {fm.rfc_state.value}"
                ),
                path=rfc_path,
                suggestion="run `irminsul change transition <id> accepted --confirm` first",
            )
        )
    blockers.extend(report.blockers)

    promotions: list[Promotion] = []
    section = graph.requirements.get(node.id)
    if section is not None and section.disposition is None:
        promotions, promotion_blockers = _plan_promotions(
            graph, repo_root, node, section.requirements, bindings, owners
        )
        blockers.extend(promotion_blockers)

    declared_req_ids = {
        req.req_id for req in (section.requirements if section else ()) if req.req_id
    }
    for flag, supplied in (("--anchor", bindings), ("--owner", owners)):
        for req_id in sorted(set(supplied) - declared_req_ids):
            blockers.append(
                Issue(
                    code="unknown-requirement",
                    message=(
                        f"{flag} names requirement '{req_id}' which this RFC does not declare"
                    ),
                    path=rfc_path,
                )
            )

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
            component_fixes.append(implements_fix(graph.nodes[promotion.owner], node.id))
        for target in RfcFollowThroughCheck().missing_implements(graph, node):
            if target.id in backlinked:
                continue
            backlinked.add(target.id)
            component_fixes.append(implements_fix(target, node.id))
        if not already_implemented:
            rfc_fixes.append(
                Fix(
                    path=node.path,
                    description=f"set rfc_state: implemented in {rfc_path}",
                    apply=setter("rfc_state", RfcStateEnum.implemented.value),
                    requires_confirm=True,
                )
            )
            rfc_fixes.extend(stable_status_fixes(node))

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
        report=report,
        notes=tuple(notes),
    )


def _plan_promotions(
    graph: DocGraph,
    repo_root: Path,
    node: DocNode,
    requirements: tuple[Requirement, ...],
    bindings: dict[str, list[str]],
    owners: dict[str, list[str]],
) -> tuple[list[Promotion], list[Issue]]:
    blockers: list[Issue] = []
    promotions: list[Promotion] = []
    rfc_path = node.path.as_posix()
    declared = list(node.frontmatter.affects or [])

    rules, _ = retirement_registry(graph)
    resolved_by = node.frontmatter.resolved_by
    record = graph.doc_at(resolved_by) if resolved_by else None

    for req in requirements:
        if req.req_id is None:
            continue  # grammar blockers already cover this
        global_id = global_requirement_id(node.id, req.req_id)
        req_bindings = bindings.get(req.req_id, [])
        owner_choices = owners.get(req.req_id, [])

        marker_payloads: list[str] = []
        binding_owner_candidates: set[str] = set()
        binding_claimants: set[str] = set()

        if req.provenance == "code":
            if not req_bindings:
                blockers.append(
                    Issue(
                        code="missing-binding",
                        message=(
                            f"code-provenance requirement '{req.req_id}' has no confirmed binding"
                        ),
                        path=rfc_path,
                        suggestion=(
                            f"pass --anchor {req.req_id}=<path>#<symbol> for the code "
                            "and the tests you read"
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
                        Issue(
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
                for claim_node, _, _ in most_specific_claims(graph.claims.get(path_part, [])):
                    binding_claimants.add(claim_node.id)
                    if claim_node.id in declared:
                        binding_owner_candidates.add(claim_node.id)
        elif req_bindings:
            blockers.append(
                Issue(
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
            sorted(binding_claimants),
            declared,
            blockers,
            rfc_path,
        )
        if owner is None:
            continue
        owner_node = graph.nodes.get(owner)
        if owner_node is None:
            continue  # unknown-component blockers already cover this

        text = _first_paragraph(req.text) or req.title
        if record is not None:
            text = link_retired_mentions(
                text, rules, record.path, _relative_link(owner_node.path, record.path)
            )
        promotion = Promotion(
            global_id=global_id,
            owner=owner,
            owner_path=owner_node.path,
            text=text,
            provenance=req.provenance or "code",
            anchors=tuple(marker_payloads),
            already_promoted=f"**{global_id}**" in owner_node.body,
            implements_present=node.id in owner_node.frontmatter.implements,
        )
        promotions.append(promotion)
        if not promotion.already_promoted:
            blockers.extend(_retired_reference_blockers(node, promotion, rules))

    return promotions, blockers


def _choose_owner(
    req_id: str,
    owner_choices: list[str],
    candidates: list[str],
    claimants: list[str],
    declared: list[str],
    blockers: list[Issue],
    rfc_path: str,
) -> str | None:
    if owner_choices:
        distinct = sorted(set(owner_choices))
        if len(distinct) > 1:
            blockers.append(
                Issue(
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
                Issue(
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
            Issue(
                code="no-owner",
                message=(f"requirement '{req_id}' has no candidate owner: `affects` is empty"),
                path=rfc_path,
                suggestion="declare the owning component in `affects`",
            )
        )
        return None
    if candidates:
        message = (
            f"requirement '{req_id}' has multiple plausible owners: {', '.join(candidates)}; "
            "an explicit choice is required"
        )
        suggestion = f"pass --owner {req_id}=<one of: {', '.join(candidates)}>"
    else:
        claimed = (
            f"its bindings are claimed by {', '.join(claimants)}, which `affects` does not declare"
            if claimants
            else "no component claims any of its bindings, so `affects` is the only source of one"
        )
        message = (
            f"requirement '{req_id}' has no plausible owner: {claimed}; "
            "an explicit choice is required"
        )
        suggestion = f"pass --owner {req_id}=<one of: {', '.join(declared)}>"
        if claimants:
            suggestion += f", or declare {', '.join(claimants)} in `affects`"
    blockers.append(
        Issue(code="ambiguous-owner", message=message, path=rfc_path, suggestion=suggestion)
    )
    return None


def _first_paragraph(text: str) -> str:
    for chunk in text.split("\n\n"):
        cleaned = " ".join(line.strip() for line in chunk.splitlines()).strip()
        if cleaned:
            return cleaned
    return ""


def _relative_link(from_path: Path, to_path: Path) -> str:
    return os.path.relpath(to_path, from_path.parent).replace("\\", "/")


def _claim_line(node: DocNode, promotion: Promotion) -> str:
    link = _relative_link(promotion.owner_path, node.path)
    return (
        f"- **{promotion.global_id}** — {promotion.text} "
        f"(provenance: {promotion.provenance}; [RFC]({link}))"
    )


def _retired_reference_blockers(
    node: DocNode, promotion: Promotion, rules: list[RetirementRule]
) -> list[Issue]:
    """What `retired-references` would still report on the claim line about to be written."""
    return [
        Issue(
            code="promoted-retired-reference",
            message=(
                f"promoting {promotion.global_id} would put the retired {rule.entry.kind.value} "
                f"'{rule.phrase}' (declared by {rule.owner.path.as_posix()}) into "
                f"{promotion.owner_path.as_posix()}, where `retired-references` reports it"
            ),
            path=node.path.as_posix(),
            suggestion=(
                f"reword the requirement to drop '{rule.phrase}', or write the claim into "
                f"{promotion.owner_path.as_posix()} yourself with '{rule.phrase}' linked to "
                f"{rule.owner.path.as_posix()}; finalize skips a claim that is already there"
            ),
        )
        for rule in reported_retirements(_claim_line(node, promotion), promotion.owner_path, rules)
    ]


def _promotion_fix(node: DocNode, promotion: Promotion) -> Fix:
    entry_lines = [_claim_line(node, promotion)]
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
