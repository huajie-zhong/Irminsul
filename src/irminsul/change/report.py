"""Change lifecycle reports: `change status` and `change verify`.

One builder produces one report shape for both commands. The report separates
three categories deliberately: mechanical blockers (deterministic, block a
transition), evidence (derived facts an agent can inspect), and semantic-review
clues (questions only an agent or human can answer). The deterministic result
may say `mechanically_ready_for`; it never claims behavior is correct. The blockers
are `gate`'s for the RFC's next state, the same function finalization asks.
"""

from __future__ import annotations

import json
import os
from collections import Counter
from collections.abc import Mapping
from dataclasses import asdict, dataclass
from enum import StrEnum
from pathlib import Path

from irminsul.change.footprint import Footprint, touched_components
from irminsul.change.gate import NEXT_STATE, Gate, Issue, declared_docs, gate, step_gate
from irminsul.checks import Severity, sort_findings
from irminsul.config import IrminsulConfig
from irminsul.docgraph import DocGraph, DocNode, build_graph, is_rfc, resolve_doc_target
from irminsul.docgraph_index import Task as TaskType
from irminsul.docgraph_index import TasksSection, global_requirement_id
from irminsul.errors import UserError
from irminsul.frontmatter import (
    RFC_OPEN_STATES,
    RFC_STATE_TRANSITIONS,
    RfcStateEnum,
)
from irminsul.git.changes import (
    ChangedPaths,
    GitChangesError,
    changed_since,
    working_tree_changed_paths,
)
from irminsul.git.reader import GitReader

REPORT_VERSION = 1

# Environment variables consulted for a CI-provided diff base, in order.
_CI_BASE_ENV_VARS = ("IRMINSUL_BASE_REF", "GITHUB_BASE_REF")


class ChangeError(UserError):
    """Raised by the change commands; the CLI prints it with its exit code."""


class EvidenceKind(StrEnum):
    changed_source = "changed-source"
    changed_test = "changed-test"
    """A recommended test file changed — not that it ran, passed, or covers the task it
    sits beside."""
    changed_doc = "changed-doc"
    unowned_source = "unowned-source"


class BaselineSource(StrEnum):
    base_ref = "base-ref"
    ci = "ci"
    local = "local"
    committed = "committed"
    unknown = "unknown"


class ReadyFor(StrEnum):
    accepted = "accepted"
    implemented = "implemented"
    none = "none"


@dataclass(frozen=True)
class EvidenceItem:
    kind: EvidenceKind
    path: str
    component: str | None = None


@dataclass(frozen=True)
class ReviewClue:
    question: str
    evidence: tuple[str, ...] = ()


@dataclass(frozen=True)
class ChangeBaseline:
    source: BaselineSource
    ref: str | None
    changed_paths: tuple[str, ...] | None
    """None when no baseline could be resolved — never rendered as a clean diff."""


@dataclass(frozen=True)
class RequirementItem:
    id: str | None
    global_id: str | None
    title: str
    provenance: str | None
    scenarios: int
    binding: str | None


@dataclass(frozen=True)
class RequirementsReport:
    disposition: str | None
    items: tuple[RequirementItem, ...]


@dataclass(frozen=True)
class TaskItem:
    id: str
    text: str
    req: str | None
    component: str | None
    source_evidence: tuple[str, ...] | None
    """None when nothing was measured, never an empty tuple that reads as a measured zero."""
    changed_tests: tuple[str, ...] | None
    review_clue: str | None


@dataclass(frozen=True)
class TaskSummary:
    total: int
    with_source_evidence: int | None
    with_changed_tests: int | None


@dataclass(frozen=True)
class TasksReport:
    items: tuple[TaskItem, ...]
    evidence_measured: bool
    summary: TaskSummary


@dataclass(frozen=True)
class ScopedFinding:
    check: str
    message: str
    path: str | None
    suggestion: str | None


@dataclass(frozen=True)
class DebtCount:
    """Warnings of one check unrelated to this change, visible without gating the transition;
    an error is a blocker, never debt."""

    check: str
    findings: int


@dataclass(frozen=True)
class ChangeReport:
    version: int
    change: str
    path: str
    title: str
    state: RfcStateEnum
    affects: tuple[str, ...] | None
    direction: str | None
    resolved_by: str | None
    valid_transitions: tuple[str, ...]
    baseline: ChangeBaseline
    footprint: Footprint | None
    declared_untouched: tuple[str, ...] = ()
    touched_undeclared: tuple[str, ...] = ()
    blockers: tuple[Issue, ...] = ()
    evidence: tuple[EvidenceItem, ...] = ()
    semantic_review: tuple[ReviewClue, ...] = ()
    mechanically_ready_for: ReadyFor = ReadyFor.none
    repository_debt: tuple[DebtCount, ...] = ()
    next_actions: tuple[str, ...] = ()
    requirements: RequirementsReport | None = None
    tasks: TasksReport | None = None
    scoped_findings: tuple[ScopedFinding, ...] = ()


def find_rfc_node(graph: DocGraph, config: IrminsulConfig, change: str) -> DocNode:
    """Resolve a structured lifecycle RFC by doc id or path, for the change commands."""
    path = resolve_doc_target(graph, change)
    node = graph.by_path.get(Path(path)) if path is not None else None
    if node is None:
        raise ChangeError(f"no RFC found for '{change}'")
    if not is_rfc(node, config):
        raise ChangeError(f"'{change}' resolves to {node.path.as_posix()}, not an RFC")
    if node.frontmatter.rfc_state is None:
        raise ChangeError(f"'{node.id}' has no rfc_state; it is not a change artifact")
    return node


@dataclass(frozen=True)
class ResolvedBase:
    """A resolved baseline with the change it was read from, so a caller that builds a
    range from it asks git once."""

    baseline: ChangeBaseline
    since: ChangedPaths | None
    """None when the baseline is unknown, and when the project has no history of its own
    to diff, such as a repository with no commits or a project below its git root, whose
    working tree is all there is to read."""


def resolve_base(
    git: GitReader,
    repo_root: Path,
    base_ref: str | None,
    *,
    env: Mapping[str, str] | None = None,
    committed_only: bool = False,
) -> ResolvedBase:
    """Resolve the diff baseline: explicit `--base-ref`, CI base ref, or `HEAD`.

    The change runs from the merge base to the working tree, uncommitted work included, or
    to `HEAD` under `committed_only`. With no base, `committed_only` ends the range where it
    starts: nothing uncommitted is a change and no commit is named, so the answer is the
    `committed` baseline with no paths. Never guesses a clean result otherwise — an
    unresolvable baseline is `unknown`, not empty.
    """
    if base_ref is not None:
        since = changed_since(git, repo_root, base_ref, committed_only=committed_only)
        if since is None:
            return ResolvedBase(ChangeBaseline(BaselineSource.unknown, base_ref, None), None)
        return _resolved(BaselineSource.base_ref, base_ref, since)

    environ = env if env is not None else os.environ
    for var in _CI_BASE_ENV_VARS:
        ci_ref = environ.get(var, "").strip()
        if not ci_ref:
            continue
        for candidate in (ci_ref, f"origin/{ci_ref}"):
            since = changed_since(git, repo_root, candidate, committed_only=committed_only)
            if since is not None:
                return _resolved(BaselineSource.ci, candidate, since)
        return ResolvedBase(ChangeBaseline(BaselineSource.unknown, ci_ref, None), None)

    if committed_only:
        return ResolvedBase(ChangeBaseline(BaselineSource.committed, None, ()), None)
    since = changed_since(git, repo_root, "HEAD")
    if since is not None:
        return _resolved(BaselineSource.local, None, since)
    try:
        local = working_tree_changed_paths(git, repo_root)
    except GitChangesError:
        return ResolvedBase(ChangeBaseline(BaselineSource.unknown, None, None), None)
    return ResolvedBase(ChangeBaseline(BaselineSource.local, None, tuple(local)), None)


def resolve_change_baseline(
    git: GitReader,
    repo_root: Path,
    base_ref: str | None,
    *,
    env: Mapping[str, str] | None = None,
    committed_only: bool = False,
) -> ChangeBaseline:
    return resolve_base(git, repo_root, base_ref, env=env, committed_only=committed_only).baseline


def _resolved(source: BaselineSource, ref: str | None, since: ChangedPaths) -> ResolvedBase:
    return ResolvedBase(ChangeBaseline(source, ref, tuple(sorted(since.changed))), since)


def build_change_report(
    repo_root: Path,
    config: IrminsulConfig,
    change: str,
    *,
    base_ref: str | None = None,
    env: Mapping[str, str] | None = None,
    graph: DocGraph | None = None,
    target: RfcStateEnum | None = None,
    next_step: bool = False,
    committed_only: bool = False,
) -> ChangeReport:
    """The report on one RFC, blocked by `gate` for `target`: its next state by default.

    With `next_step` it blocks on exactly what that lifecycle step does, `step_gate`, as
    `change status` reports: nothing for a terminal RFC. The footprint is the change from
    the baseline's merge base to the working tree, or to `HEAD` under `committed_only`.
    """
    if graph is None:
        graph = build_graph(repo_root, config, committed_only=committed_only)
    node = find_rfc_node(graph, config, change)
    fm = node.frontmatter
    assert fm.rfc_state is not None
    state = fm.rfc_state
    target = target or NEXT_STATE.get(state)

    baseline = resolve_change_baseline(
        graph.git, repo_root, base_ref, env=env, committed_only=committed_only
    )
    if not next_step:
        judged = gate(graph, node, target, baseline)
    elif target is not None:
        judged = step_gate(graph, node, target, baseline)
    else:
        judged = Gate(())
    footprint = judged.footprint
    if footprint is None and baseline.changed_paths is not None:
        footprint = touched_components(graph, frozenset(baseline.changed_paths))

    clues: list[ReviewClue] = []
    evidence: list[EvidenceItem] = []
    next_actions: list[str] = []
    affects = tuple(fm.affects) if fm.affects is not None else None

    requirements: RequirementsReport | None = None
    section = graph.requirements.get(node.id)
    if section is not None:
        requirements = RequirementsReport(
            disposition=section.disposition,
            items=tuple(
                RequirementItem(
                    id=req.req_id,
                    global_id=global_requirement_id(node.id, req.req_id) if req.req_id else None,
                    title=req.title,
                    provenance=req.provenance,
                    scenarios=len(req.scenarios),
                    binding=(
                        "planned/unbound"
                        if req.provenance == "code" and state in RFC_OPEN_STATES
                        else None
                    ),
                )
                for req in section.requirements
            ),
        )
        for req in section.requirements:
            if len(req.scenarios) == 1:
                clues.append(
                    ReviewClue(
                        question=(
                            f"requirement '{req.req_id or req.title}' has a single "
                            "scenario; is a negative or failure scenario missing?"
                        ),
                        evidence=(node.path.as_posix(),),
                    )
                )

    tasks_section = graph.tasks.get(node.id)
    tasks = (
        _task_evidence(node, tasks_section, affects, footprint, clues)
        if tasks_section is not None
        else None
    )

    declared_untouched: tuple[str, ...] = ()
    touched_undeclared: tuple[str, ...] = ()
    if footprint is not None:
        for component, files in footprint.touched.items():
            evidence.extend(EvidenceItem(EvidenceKind.changed_source, f, component) for f in files)
        for component, files in footprint.changed_tests.items():
            evidence.extend(EvidenceItem(EvidenceKind.changed_test, f, component) for f in files)
        evidence.extend(EvidenceItem(EvidenceKind.changed_doc, d) for d in footprint.changed_docs)
        evidence.extend(
            EvidenceItem(EvidenceKind.unowned_source, u) for u in footprint.unowned_source
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

    scoped_findings, repository_debt = _partition_configured_findings(graph, judged, node, baseline)
    ready = ReadyFor(target.value) if target is not None and not judged.issues else ReadyFor.none

    if state == RfcStateEnum.draft:
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
    elif state == RfcStateEnum.accepted:
        if ready == ReadyFor.implemented:
            next_actions.append(
                f"irminsul change finalize {node.id} "
                "--anchor <req>=<path>#<symbol> --confirm (after semantic review)"
            )
        else:
            next_actions.append(f"irminsul change verify {node.id} --base-ref <ref>")

    return ChangeReport(
        version=REPORT_VERSION,
        change=node.id,
        path=node.path.as_posix(),
        title=fm.title,
        state=state,
        affects=affects,
        direction=fm.direction.value if fm.direction else None,
        resolved_by=fm.resolved_by,
        valid_transitions=tuple(
            sorted(s.value for s in RFC_STATE_TRANSITIONS.get(state, frozenset()))
        ),
        baseline=baseline,
        footprint=footprint,
        declared_untouched=declared_untouched,
        touched_undeclared=touched_undeclared,
        blockers=judged.issues,
        evidence=tuple(evidence),
        semantic_review=tuple(clues),
        mechanically_ready_for=ready,
        repository_debt=repository_debt,
        next_actions=tuple(next_actions),
        requirements=requirements,
        tasks=tasks,
        scoped_findings=scoped_findings,
    )


def _partition_configured_findings(
    graph: DocGraph,
    judged: Gate,
    node: DocNode,
    baseline: ChangeBaseline,
) -> tuple[tuple[ScopedFinding, ...], tuple[DebtCount, ...]]:
    """Split enabled warnings into change-scoped findings and repository debt.

    A warning the gate judged itself is already its blocker, and is not repeated. The
    rest concern this change — the RFC, a doc it declares, or a changed path — or are
    counted as debt, visible without gating the transition.
    """
    scope_paths = set(declared_docs(graph, node))
    if baseline.changed_paths is not None:
        scope_paths.update(baseline.changed_paths)

    scoped: list[ScopedFinding] = []
    debt: Counter[str] = Counter()
    findings = judged.run.findings if judged.run is not None else []
    for finding in sort_findings(findings):
        # Errors are already blockers; only warnings are scoped or counted as debt.
        if finding.severity is not Severity.warning or judged.covers(finding):
            continue
        finding_path = finding.path.as_posix() if finding.path else None
        if finding_path in scope_paths or finding.doc_id == node.id:
            scoped.append(
                ScopedFinding(finding.check, finding.message, finding_path, finding.suggestion)
            )
        else:
            debt[finding.check] += 1

    return tuple(scoped), tuple(DebtCount(check, n) for check, n in sorted(debt.items()))


def _task_evidence(
    node: DocNode,
    tasks_section: TasksSection,
    affects: tuple[str, ...] | None,
    footprint: Footprint | None,
    clues: list[ReviewClue],
) -> TasksReport:
    """Per-task mechanical evidence: evidence labels, never
    completion labels. Several tasks may share one requirement and therefore
    the same changed files — semantics stay with the reviewer.

    With no diff baseline nothing was measured, so evidence and counts are
    `None` (unknown), never an empty list that reads as a measured zero.
    """
    tasks = tasks_section.tasks
    declared = tuple(affects or ())
    items: list[TaskItem] = []
    tasks_with_source = 0
    tasks_with_test = 0

    for task in tasks:
        related = (task.component_ref,) if task.component_ref else declared
        source_evidence: tuple[str, ...] | None = None
        changed_tests: tuple[str, ...] | None = None
        review_clue: str | None = None

        if footprint is not None:
            source_evidence = tuple(
                sorted({f for c in related for f in footprint.touched.get(c, ())})
            )
            changed_tests = tuple(
                sorted({f for c in related for f in footprint.changed_tests.get(c, ())})
            )
            tasks_with_source += bool(source_evidence)
            tasks_with_test += bool(changed_tests)

            if not source_evidence:
                review_clue = f"no changed source is associated with {_task_scope(task)}"
            elif not changed_tests:
                review_clue = "inspect implementation and add or identify scenario coverage"
            else:
                review_clue = "confirm the changed tests assert this task's scenario, and run them"
            clues.append(
                ReviewClue(
                    question=f"task '{task.task_id}': {review_clue}",
                    evidence=(*source_evidence, *changed_tests) or (node.path.as_posix(),),
                )
            )

        items.append(
            TaskItem(
                id=task.task_id,
                text=task.text,
                req=task.req_ref,
                component=task.component_ref,
                source_evidence=source_evidence,
                changed_tests=changed_tests,
                review_clue=review_clue,
            )
        )

    measured = footprint is not None
    return TasksReport(
        items=tuple(items),
        evidence_measured=measured,
        summary=TaskSummary(
            total=len(tasks),
            with_source_evidence=tasks_with_source if measured else None,
            with_changed_tests=tasks_with_test if measured else None,
        ),
    )


def _task_scope(task: TaskType) -> str:
    if task.component_ref:
        return "this task's component"
    if task.req_ref:
        return "this task's requirement"
    return (
        "any declared affected component (this task references neither a "
        "requirement nor a component)"
    )


def change_report_to_json(report: ChangeReport) -> str:
    payload: dict[str, object] = {
        "version": report.version,
        "change": report.change,
        "path": report.path,
        "title": report.title,
        "state": report.state,
        "affects": report.affects,
        "direction": report.direction,
        "resolved_by": report.resolved_by,
        "valid_transitions": report.valid_transitions,
        "baseline": asdict(report.baseline),
        "declared_untouched": report.declared_untouched,
        "touched_undeclared": report.touched_undeclared,
        "blockers": [
            {"code": b.code, "message": b.message, "path": b.path, "suggestion": b.suggestion}
            for b in report.blockers
        ],
        "evidence": [asdict(e) for e in report.evidence],
        "semantic_review": [asdict(c) for c in report.semantic_review],
        "mechanically_ready_for": report.mechanically_ready_for,
        "repository_debt": [asdict(d) for d in report.repository_debt],
        "next_actions": report.next_actions,
    }
    if report.requirements is not None:
        payload["requirements"] = asdict(report.requirements)
    if report.tasks is not None:
        payload["tasks"] = asdict(report.tasks)
    if report.scoped_findings:
        payload["scoped_findings"] = [asdict(s) for s in report.scoped_findings]
    return json.dumps(payload, indent=2)


def format_change_status_plain(report: ChangeReport) -> str:
    lines = [
        f"{report.change}: {report.title}",
        f"  state: {report.state}",
        f"  affects: {_affects_line(report.affects)}",
        f"  resolved_by: {report.resolved_by or '-'}",
        f"  valid transitions: {', '.join(report.valid_transitions) or '(terminal)'}",
        f"  baseline: {_baseline_line(report.baseline)}",
    ]
    if report.blockers:
        lines.append("  blockers:")
        lines.extend(f"    [{b.code}] {b.message}" for b in report.blockers)
    lines.append(f"  mechanically ready for: {report.mechanically_ready_for}")
    if report.tasks is not None:
        lines.append(f"  tasks: {_task_summary(report.tasks)}")
    if report.evidence:
        lines.append(f"  evidence: {len(report.evidence)} item(s); run `change verify` for detail")
    if report.scoped_findings:
        lines.append(
            f"  findings about this change: {len(report.scoped_findings)}; "
            "run `change verify` for detail"
        )
    if report.next_actions:
        lines.append("  next:")
        lines.extend(f"    {action}" for action in report.next_actions)
    return "\n".join(lines)


def format_change_verify_plain(report: ChangeReport) -> str:
    lines = [
        f"{report.change}: {report.title}",
        f"  state: {report.state}",
        f"  affects: {_affects_line(report.affects)}",
        f"  baseline: {_baseline_line(report.baseline)}",
    ]
    lines.extend(_requirements_lines(report.requirements))
    lines.extend(_tasks_lines(report.tasks))
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
    if report.scoped_findings:
        lines.append(f"  findings about this change: {len(report.scoped_findings)}")
        for item in report.scoped_findings:
            location = f"{item.path}: " if item.path else ""
            lines.append(f"    [{item.check}] {location}{item.message}")
            if item.suggestion:
                lines.append(f"      -> {item.suggestion}")
    if report.repository_debt:
        debt = ", ".join(f"{d.check} {d.findings}" for d in report.repository_debt)
        lines.append(f"  repository debt (unrelated): {debt}")
    if report.next_actions:
        lines.append("  next:")
        lines.extend(f"    {action}" for action in report.next_actions)
    return "\n".join(lines)


def _task_summary(tasks: TasksReport) -> str:
    total = tasks.summary.total
    if not tasks.evidence_measured:
        return f"{total} declared; evidence unknown (no diff baseline)"
    return (
        f"{tasks.summary.with_source_evidence}/{total} with source evidence, "
        f"{tasks.summary.with_changed_tests}/{total} with changed tests"
    )


def _evidence_line(label: str, paths: tuple[str, ...] | None) -> str:
    value = "unknown (no diff baseline)" if paths is None else ", ".join(paths) or "none"
    return f"      {label} {value}"


def _tasks_lines(tasks: TasksReport | None) -> list[str]:
    if tasks is None:
        return []
    lines = [f"  tasks: {_task_summary(tasks)}"]
    for item in tasks.items:
        ref = ""
        if item.req:
            ref = f" (req: {item.req})"
        elif item.component:
            ref = f" (component: {item.component})"
        lines.append(f"    {item.id} {item.text}{ref}")
        lines.append(_evidence_line("source evidence:", item.source_evidence))
        lines.append(_evidence_line("changed tests:  ", item.changed_tests))
        if item.review_clue:
            lines.append(f"      review clue:     {item.review_clue}")
    return lines


def _requirements_lines(requirements: RequirementsReport | None) -> list[str]:
    if requirements is None:
        return []
    if requirements.disposition:
        return [f"  requirements: {requirements.disposition}"]
    lines = [f"  requirements: {len(requirements.items)}"]
    for item in requirements.items:
        binding = f" [{item.binding}]" if item.binding else ""
        lines.append(
            f"    {item.id or '(no id)'}: {item.title} "
            f"(provenance {item.provenance or '?'}, "
            f"{item.scenarios} scenario(s)){binding}"
        )
    return lines


def _affects_line(affects: tuple[str, ...] | None) -> str:
    if affects is None:
        return "(not declared)"
    return ", ".join(affects) if affects else "[] (no owned source)"


def _baseline_line(baseline: ChangeBaseline) -> str:
    if baseline.source == BaselineSource.committed:
        return (
            "committed only, no base: no change is judged and nothing uncommitted is read; "
            "pass --base-ref <ref> to judge a branch's commits"
        )
    if baseline.changed_paths is None:
        return f"unknown{f' (ref {baseline.ref})' if baseline.ref else ''}"
    ref = f" {baseline.ref}" if baseline.ref else ""
    return f"{baseline.source}{ref}, {len(baseline.changed_paths)} changed path(s)"
