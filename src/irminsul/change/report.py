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
from irminsul.config import IrminsulConfig
from irminsul.docgraph import DocGraph, DocNode, build_graph
from irminsul.docgraph_index import Task as TaskType
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
    docs_root = (config.paths.docs_root or "docs").replace("\\", "/").strip("/")
    rfc_prefix = f"{docs_root}/80-evolution/rfcs/"

    node = graph.nodes.get(change)
    if node is None:
        normalized = change.replace("\\", "/")
        node = graph.by_path.get(Path(normalized))
    if node is None and change.isdigit():
        matches = [
            candidate
            for candidate in graph.nodes.values()
            if candidate.id.startswith(f"{change}-")
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

    extra: dict[str, object] = {}
    section = graph.requirements.get(node.id)
    if canonical in (RfcStateEnum.draft, RfcStateEnum.accepted):
        blockers.extend(requirement_blockers(graph, node))
    if section is not None:
        extra["requirements"] = {
            "disposition": section.disposition,
            "items": [
                {
                    "id": req.req_id,
                    "global_id": f"{node.id}#{req.req_id}" if req.req_id else None,
                    "title": req.title,
                    "provenance": req.provenance,
                    "scenarios": len(req.scenarios),
                    "binding": (
                        "planned/unbound"
                        if req.provenance == "code" and canonical != RfcStateEnum.implemented
                        else None
                    ),
                }
                for req in section.requirements
            ],
        }
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

    tasks = graph.tasks.get(node.id)
    if tasks is not None:
        extra["tasks"] = _task_evidence(node, tasks, affects, footprint, clues)

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
        clues.append(
            ReviewClue(
                question=(
                    "no diff baseline could be resolved; pass --base-ref (or run from "
                    "a git worktree) to derive implementation evidence"
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
        extra=extra,
    )


def _task_evidence(
    node: DocNode,
    tasks: tuple[TaskType, ...],
    affects: tuple[str, ...] | None,
    footprint: Footprint | None,
    clues: list[ReviewClue],
) -> dict[str, object]:
    """Per-task mechanical evidence (RFC 0031): evidence labels, never
    completion labels. Several tasks may share one requirement and therefore
    the same changed files — semantics stay with the reviewer."""
    declared = tuple(affects or ())
    items: list[dict[str, object]] = []
    tasks_with_source = 0
    tasks_with_test = 0

    for task in tasks:
        related = (task.component_ref,) if task.component_ref else declared
        source_evidence: list[str] = []
        test_evidence: list[str] = []
        if footprint is not None:
            for component in related:
                source_evidence.extend(footprint.touched.get(component, ()))
                test_evidence.extend(footprint.changed_tests.get(component, ()))
        source_evidence = sorted(set(source_evidence))
        test_evidence = sorted(set(test_evidence))
        tasks_with_source += bool(source_evidence)
        tasks_with_test += bool(test_evidence)

        review_clue: str | None = None
        if footprint is not None:
            if not source_evidence:
                review_clue = (
                    "no changed source is associated with this task's "
                    f"{'component' if task.component_ref else 'requirement'}"
                )
            elif not test_evidence:
                review_clue = "inspect implementation and add or identify scenario coverage"
            else:
                review_clue = "confirm the changed tests assert this task's scenario"
        if review_clue is not None:
            clues.append(
                ReviewClue(
                    question=f"task '{task.task_id}': {review_clue}",
                    evidence=tuple(source_evidence + test_evidence) or (node.path.as_posix(),),
                )
            )

        items.append(
            {
                "id": task.task_id,
                "text": task.text,
                "req": task.req_ref,
                "component": task.component_ref,
                "source_evidence": source_evidence,
                "test_evidence": test_evidence,
                "review_clue": review_clue,
            }
        )

    return {
        "items": items,
        "summary": {
            "total": len(tasks),
            "with_source_evidence": tasks_with_source,
            "with_test_evidence": tasks_with_test,
        },
    }


def requirement_blockers(graph: DocGraph, node: DocNode) -> list[Blocker]:
    """Requirement-contract blockers shared by reports and transitions (RFC 0030).

    Acceptance freezes the contract to implement: the RFC needs either
    well-formed requirements or an explicit no-new-behavior disposition, and
    grammar findings that warn elsewhere block here.
    """
    from irminsul.checks.requirement_grammar import (
        RequirementGrammarCheck,
        requirement_grammar_findings,
    )

    section = graph.requirements.get(node.id)
    if section is None:
        return [
            Blocker(
                code="missing-requirements",
                message=(
                    "no `## Requirements` section: add requirement blocks or the "
                    "explicit sentence 'No new behavioral requirements: ...'"
                ),
                path=node.path.as_posix(),
                suggestion="see RFC 0030 for the requirement/scenario grammar",
            )
        ]

    findings = requirement_grammar_findings(node, section, check_name=RequirementGrammarCheck.name)
    tasks = graph.tasks.get(node.id)
    if tasks is not None:
        from irminsul.checks.requirement_grammar import task_grammar_findings

        findings.extend(
            task_grammar_findings(node, tasks, section, check_name=RequirementGrammarCheck.name)
        )
    return [
        Blocker(
            code=f"requirement-grammar:{finding.category}",
            message=finding.message,
            path=node.path.as_posix(),
            suggestion=finding.suggestion,
        )
        for finding in findings
    ]


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
    summary = _task_summary(report)
    if summary is not None:
        lines.append(f"  tasks: {summary}")
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
    lines.extend(_requirements_lines(report))
    lines.extend(_tasks_lines(report))
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


def _task_summary(report: ChangeReport) -> str | None:
    payload = report.extra.get("tasks")
    if not isinstance(payload, dict):
        return None
    summary = payload.get("summary")
    if not isinstance(summary, dict):
        return None
    total = summary.get("total")
    return (
        f"{summary.get('with_source_evidence')}/{total} with source evidence, "
        f"{summary.get('with_test_evidence')}/{total} with test evidence"
    )


def _tasks_lines(report: ChangeReport) -> list[str]:
    payload = report.extra.get("tasks")
    if not isinstance(payload, dict):
        return []
    items = payload.get("items")
    if not isinstance(items, list):
        return []
    summary = _task_summary(report)
    lines = [f"  tasks: {summary}" if summary else "  tasks:"]
    for item in items:
        if not isinstance(item, dict):
            continue
        ref = ""
        if item.get("req"):
            ref = f" (req: {item['req']})"
        elif item.get("component"):
            ref = f" (component: {item['component']})"
        lines.append(f"    {item.get('id')} {item.get('text')}{ref}")
        source = item.get("source_evidence") or []
        tests = item.get("test_evidence") or []
        lines.append(f"      source evidence: {', '.join(source) if source else 'none'}")
        lines.append(f"      test evidence:   {', '.join(tests) if tests else 'none'}")
        if item.get("review_clue"):
            lines.append(f"      review clue:     {item['review_clue']}")
    return lines


def _requirements_lines(report: ChangeReport) -> list[str]:
    payload = report.extra.get("requirements")
    if not isinstance(payload, dict):
        return []
    disposition = payload.get("disposition")
    if disposition:
        return [f"  requirements: {disposition}"]
    items = payload.get("items")
    if not isinstance(items, list):
        return []
    lines = [f"  requirements: {len(items)}"]
    for item in items:
        if not isinstance(item, dict):
            continue
        binding = f" [{item['binding']}]" if item.get("binding") else ""
        lines.append(
            f"    {item.get('id') or '(no id)'}: {item.get('title')} "
            f"(provenance {item.get('provenance') or '?'}, "
            f"{item.get('scenarios')} scenario(s)){binding}"
        )
    return lines


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
