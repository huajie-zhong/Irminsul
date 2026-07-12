"""Change lifecycle reports (RFC 0029): `change status` and `change verify`.

One builder produces one report shape for both commands. The report separates
three categories deliberately: mechanical blockers (deterministic, block a
transition), evidence (derived facts an agent can inspect), and semantic-review
clues (questions only an agent or human can answer). The deterministic result
may say `mechanically_ready_for`; it never claims behavior is correct.
"""

from __future__ import annotations

import json
import os
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path

from irminsul.change.footprint import Footprint, touched_components
from irminsul.checks import HARD_REGISTRY, Finding, Severity, sort_findings
from irminsul.config import IrminsulConfig, docs_root_prefix
from irminsul.docgraph import DocGraph, DocNode, build_graph
from irminsul.frontmatter import (
    RFC_STATE_TRANSITIONS,
    RfcStateEnum,
    canonical_rfc_state,
)
from irminsul.git.changes import GitChangesError, working_tree_changed_paths
from irminsul.git.mtime import diff_name_only

REPORT_VERSION = 1

# Environment variables consulted for a CI-provided diff base, in order.
_CI_BASE_ENV_VARS = ("IRMINSUL_BASE_REF", "GITHUB_BASE_REF")


class ChangeError(Exception):
    """User-facing change command error."""

    def __init__(self, message: str, *, code: int = 1) -> None:
        super().__init__(message)
        self.code = code


@dataclass(frozen=True)
class Blocker:
    code: str
    message: str
    path: str | None = None
    suggestion: str | None = None


@dataclass(frozen=True)
class EvidenceItem:
    kind: str  # changed-source | changed-test | changed-doc | unowned-source
    path: str
    component: str | None = None


@dataclass(frozen=True)
class ReviewClue:
    question: str
    evidence: tuple[str, ...] = ()


@dataclass(frozen=True)
class ChangeBaseline:
    source: str  # base-ref | ci | local | unknown
    ref: str | None
    changed_paths: tuple[str, ...] | None
    """None when no baseline could be resolved — never rendered as a clean diff."""


@dataclass(frozen=True)
class ChangeReport:
    version: int
    change: str
    path: str
    title: str
    state: str
    canonical_state: str
    state_deprecated: bool
    affects: tuple[str, ...] | None
    direction: str | None
    resolved_by: str | None
    valid_transitions: tuple[str, ...]
    baseline: ChangeBaseline
    footprint: Footprint | None
    declared_untouched: tuple[str, ...] = ()
    touched_undeclared: tuple[str, ...] = ()
    blockers: tuple[Blocker, ...] = ()
    evidence: tuple[EvidenceItem, ...] = ()
    semantic_review: tuple[ReviewClue, ...] = ()
    mechanically_ready_for: str = "none"  # accepted | implemented | none
    next_actions: tuple[str, ...] = ()
    extra: dict[str, object] = field(default_factory=dict)
    """Escape hatch for later RFCs (requirements, tasks, impact) to extend the
    report without changing this dataclass on every iteration."""


def find_rfc_node(graph: DocGraph, config: IrminsulConfig, change: str) -> DocNode:
    """Resolve a change reference: doc id, numeric prefix, or repo-relative path."""
    rfc_prefix = f"{docs_root_prefix(config)}/80-evolution/rfcs/"

    node = graph.nodes.get(change)
    if node is None:
        normalized = change.replace("\\", "/")
        node = graph.by_path.get(Path(normalized))
    if node is None and change.isdigit():
        padded = change.zfill(4)
        matches = [
            candidate
            for candidate in graph.nodes.values()
            if candidate.id.startswith(f"{padded}-")
            and candidate.path.as_posix().startswith(rfc_prefix)
        ]
        if len(matches) > 1:
            ids = ", ".join(sorted(m.id for m in matches))
            raise ChangeError(f"'{change}' is ambiguous; matches: {ids}", code=2)
        node = matches[0] if matches else None

    if node is None:
        raise ChangeError(f"no RFC found for '{change}'", code=2)
    if not node.path.as_posix().startswith(rfc_prefix):
        raise ChangeError(f"'{change}' resolves to {node.path.as_posix()}, not an RFC", code=2)
    if node.frontmatter.rfc_state is None:
        raise ChangeError(f"'{node.id}' has no rfc_state; it is not a change artifact", code=2)
    return node


def resolve_change_baseline(
    repo_root: Path,
    base_ref: str | None,
    *,
    env: Mapping[str, str] | None = None,
) -> ChangeBaseline:
    """Resolve the diff baseline: explicit `--base-ref`, CI base ref, or the
    local working tree. Never guesses a clean result — an unresolvable baseline
    is `unknown`, not empty."""
    if base_ref is not None:
        changed = diff_name_only(repo_root, base_ref, "HEAD")
        if changed is None:
            return ChangeBaseline(source="unknown", ref=base_ref, changed_paths=None)
        return ChangeBaseline(source="base-ref", ref=base_ref, changed_paths=tuple(sorted(changed)))

    environ = env if env is not None else os.environ
    for var in _CI_BASE_ENV_VARS:
        ci_ref = environ.get(var, "").strip()
        if not ci_ref:
            continue
        for candidate in (ci_ref, f"origin/{ci_ref}"):
            changed = diff_name_only(repo_root, candidate, "HEAD")
            if changed is not None:
                return ChangeBaseline(
                    source="ci", ref=candidate, changed_paths=tuple(sorted(changed))
                )
        return ChangeBaseline(source="unknown", ref=ci_ref, changed_paths=None)

    try:
        local = working_tree_changed_paths(repo_root)
    except GitChangesError:
        return ChangeBaseline(source="unknown", ref=None, changed_paths=None)
    return ChangeBaseline(source="local", ref=None, changed_paths=tuple(local))


def build_change_report(
    repo_root: Path,
    config: IrminsulConfig,
    change: str,
    *,
    base_ref: str | None = None,
    env: Mapping[str, str] | None = None,
    graph: DocGraph | None = None,
) -> ChangeReport:
    if graph is None:
        graph = build_graph(repo_root, config)
    node = find_rfc_node(graph, config, change)
    fm = node.frontmatter
    assert fm.rfc_state is not None
    state = fm.rfc_state
    canonical = canonical_rfc_state(state)

    baseline = resolve_change_baseline(repo_root, base_ref, env=env)
    footprint: Footprint | None = None
    if baseline.changed_paths is not None:
        footprint = touched_components(graph, config, frozenset(baseline.changed_paths))

    blockers: list[Blocker] = []
    clues: list[ReviewClue] = []
    evidence: list[EvidenceItem] = []
    next_actions: list[str] = []

    affects = tuple(fm.affects) if fm.affects is not None else None

    if canonical in (RfcStateEnum.accepted, RfcStateEnum.implemented) and affects is None:
        blockers.append(
            Blocker(
                code="missing-affects",
                message=(
                    f"{canonical.value} RFC must declare `affects` explicitly; "
                    "use `affects: []` when no owned source changes"
                ),
                path=node.path.as_posix(),
                suggestion="add `affects: [<component ids>]` to the RFC frontmatter",
            )
        )
    for declared in affects or ():
        if declared not in graph.nodes:
            blockers.append(
                Blocker(
                    code="unknown-component",
                    message=f"`affects` entry '{declared}' does not match any doc id",
                    path=node.path.as_posix(),
                    suggestion="correct the component id in `affects`",
                )
            )

    resolved_target = None
    if fm.resolved_by is not None:
        resolved_target = graph.by_path.get(Path(fm.resolved_by.replace("\\", "/")))
        if resolved_target is None:
            blockers.append(
                Blocker(
                    code="unresolved-adr",
                    message=f"resolved_by '{fm.resolved_by}' does not exist in the graph",
                    path=node.path.as_posix(),
                    suggestion="fix the path or create the decision doc",
                )
            )
    elif canonical == RfcStateEnum.draft:
        blockers.append(
            Blocker(
                code="missing-adr",
                message="an accepted RFC must resolve to a decision record; none is declared",
                path=node.path.as_posix(),
                suggestion=(
                    "create it with `irminsul new adr <title>` and pass "
                    "--resolved-by <adr path> to `change transition`"
                ),
            )
        )

    hard_errors = _hard_errors(graph, config)
    for finding in hard_errors:
        blockers.append(
            Blocker(
                code=f"hard-check:{finding.check}",
                message=finding.message,
                path=finding.path.as_posix() if finding.path else None,
                suggestion=finding.suggestion,
            )
        )

    declared_untouched: tuple[str, ...] = ()
    touched_undeclared: tuple[str, ...] = ()
    if footprint is not None:
        for component, files in footprint.touched.items():
            evidence.extend(
                EvidenceItem(kind="changed-source", path=f, component=component) for f in files
            )
        for component, files in footprint.changed_tests.items():
            evidence.extend(
                EvidenceItem(kind="changed-test", path=f, component=component) for f in files
            )
        evidence.extend(EvidenceItem(kind="changed-doc", path=d) for d in footprint.changed_docs)
        evidence.extend(
            EvidenceItem(kind="unowned-source", path=u) for u in footprint.unowned_source
        )

        if affects is not None:
            touched_set = set(footprint.touched)
            declared_set = set(affects)
            declared_untouched = tuple(sorted(declared_set - touched_set))
            touched_undeclared = tuple(sorted(touched_set - declared_set))
            for component in declared_untouched:
                clues.append(
                    ReviewClue(
                        question=(
                            f"declared component '{component}' has no implementation "
                            "evidence in this baseline — not started, or planned scope "
                            "that was dropped?"
                        ),
                        evidence=(node.path.as_posix(),),
                    )
                )
            for component in touched_undeclared:
                clues.append(
                    ReviewClue(
                        question=(
                            f"component '{component}' changed but is absent from "
                            "`affects` — intended scope expansion or accidental side "
                            "effect?"
                        ),
                        evidence=footprint.touched[component],
                    )
                )
    else:
        blockers.append(
            Blocker(
                code="missing-baseline",
                message=(
                    "no diff baseline could be resolved, so no implementation evidence "
                    "can be derived"
                ),
                path=node.path.as_posix(),
                suggestion=(
                    "pass --base-ref <ref>, set IRMINSUL_BASE_REF, or run from a git worktree"
                ),
            )
        )

    mechanically_ready_for = "none"
    if canonical == RfcStateEnum.draft and not blockers and affects is not None:
        mechanically_ready_for = "accepted"
    if (
        canonical == RfcStateEnum.accepted
        and not blockers
        and baseline.changed_paths is not None
        and not touched_undeclared
    ):
        mechanically_ready_for = "implemented"

    if canonical == RfcStateEnum.draft:
        if affects is None:
            next_actions.append("declare `affects` in the RFC frontmatter (use [] for none)")
        if fm.resolved_by is None:
            next_actions.append(
                "create the decision record (`irminsul new adr <title>`), then "
                f"`irminsul change transition {node.id} accepted "
                "--resolved-by <adr path> --confirm`"
            )
        else:
            next_actions.append(f"irminsul change transition {node.id} accepted --confirm")
    elif canonical == RfcStateEnum.accepted:
        next_actions.append(f"irminsul change verify {node.id} --base-ref <ref>")

    return ChangeReport(
        version=REPORT_VERSION,
        change=node.id,
        path=node.path.as_posix(),
        title=fm.title,
        state=state.value,
        canonical_state=canonical.value,
        state_deprecated=state != canonical,
        affects=affects,
        direction=fm.direction.value if fm.direction else None,
        resolved_by=fm.resolved_by,
        valid_transitions=tuple(
            sorted(s.value for s in RFC_STATE_TRANSITIONS.get(canonical, frozenset()))
        ),
        baseline=baseline,
        footprint=footprint,
        declared_untouched=declared_untouched,
        touched_undeclared=touched_undeclared,
        blockers=tuple(blockers),
        evidence=tuple(evidence),
        semantic_review=tuple(clues),
        mechanically_ready_for=mechanically_ready_for,
        next_actions=tuple(next_actions),
    )


def _hard_errors(graph: DocGraph, config: IrminsulConfig) -> list[Finding]:
    findings: list[Finding] = []
    for name in config.checks.hard:
        cls = HARD_REGISTRY.get(name)
        if cls is None:
            continue
        findings.extend(cls().run(graph))
    return sort_findings([f for f in findings if f.severity == Severity.error])


def change_report_to_json(report: ChangeReport) -> str:
    payload: dict[str, object] = {
        "version": report.version,
        "change": report.change,
        "path": report.path,
        "title": report.title,
        "state": report.state,
        "canonical_state": report.canonical_state,
        "state_deprecated": report.state_deprecated,
        "affects": list(report.affects) if report.affects is not None else None,
        "direction": report.direction,
        "resolved_by": report.resolved_by,
        "valid_transitions": list(report.valid_transitions),
        "baseline": {
            "source": report.baseline.source,
            "ref": report.baseline.ref,
            "changed_paths": (
                list(report.baseline.changed_paths)
                if report.baseline.changed_paths is not None
                else None
            ),
        },
        "declared_untouched": list(report.declared_untouched),
        "touched_undeclared": list(report.touched_undeclared),
        "blockers": [
            {
                "code": b.code,
                "message": b.message,
                "path": b.path,
                "suggestion": b.suggestion,
            }
            for b in report.blockers
        ],
        "evidence": [
            {"kind": e.kind, "path": e.path, "component": e.component} for e in report.evidence
        ],
        "semantic_review": [
            {"question": c.question, "evidence": list(c.evidence)} for c in report.semantic_review
        ],
        "mechanically_ready_for": report.mechanically_ready_for,
        "next_actions": list(report.next_actions),
    }
    payload.update(report.extra)
    return json.dumps(payload, indent=2)


def format_change_status_plain(report: ChangeReport) -> str:
    lines = [
        f"{report.change}: {report.title}",
        f"  state: {_state_line(report)}",
        f"  affects: {_affects_line(report.affects)}",
        f"  resolved_by: {report.resolved_by or '-'}",
        f"  valid transitions: {', '.join(report.valid_transitions) or '(terminal)'}",
        f"  baseline: {_baseline_line(report.baseline)}",
    ]
    if report.blockers:
        lines.append("  blockers:")
        lines.extend(f"    [{b.code}] {b.message}" for b in report.blockers)
    lines.append(f"  mechanically ready for: {report.mechanically_ready_for}")
    if report.evidence:
        lines.append(f"  evidence: {len(report.evidence)} item(s); run `change verify` for detail")
    if report.next_actions:
        lines.append("  next:")
        lines.extend(f"    {action}" for action in report.next_actions)
    return "\n".join(lines)


def format_change_verify_plain(report: ChangeReport) -> str:
    lines = [
        f"{report.change}: {report.title}",
        f"  state: {_state_line(report)}",
        f"  affects: {_affects_line(report.affects)}",
        f"  baseline: {_baseline_line(report.baseline)}",
    ]
    if report.blockers:
        lines.append("  blockers:")
        for b in report.blockers:
            lines.append(f"    [{b.code}] {b.message}")
            if b.suggestion:
                lines.append(f"      -> {b.suggestion}")
    else:
        lines.append("  blockers: (none)")
    if report.evidence:
        lines.append("  evidence:")
        for e in report.evidence:
            component = f" ({e.component})" if e.component else ""
            lines.append(f"    {e.kind}: {e.path}{component}")
    else:
        lines.append("  evidence: (none)")
    if report.declared_untouched:
        lines.append(f"  declared but untouched: {', '.join(report.declared_untouched)}")
    if report.touched_undeclared:
        lines.append(f"  touched but undeclared: {', '.join(report.touched_undeclared)}")
    if report.semantic_review:
        lines.append("  semantic review:")
        lines.extend(f"    - {c.question}" for c in report.semantic_review)
    lines.append(f"  mechanically ready for: {report.mechanically_ready_for}")
    if report.next_actions:
        lines.append("  next:")
        lines.extend(f"    {action}" for action in report.next_actions)
    return "\n".join(lines)


def _state_line(report: ChangeReport) -> str:
    if report.state_deprecated:
        return f"{report.state} (deprecated alias of {report.canonical_state})"
    return report.state


def _affects_line(affects: tuple[str, ...] | None) -> str:
    if affects is None:
        return "(not declared)"
    return ", ".join(affects) if affects else "[] (no owned source)"


def _baseline_line(baseline: ChangeBaseline) -> str:
    if baseline.changed_paths is None:
        return f"unknown{f' (ref {baseline.ref})' if baseline.ref else ''}"
    ref = f" {baseline.ref}" if baseline.ref else ""
    return f"{baseline.source}{ref}, {len(baseline.changed_paths)} changed path(s)"
