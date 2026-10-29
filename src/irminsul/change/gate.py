"""The rules an RFC meets to enter a lifecycle state, each written once.

Each rule is a predicate returning `Issue`s. A check calls it with the doc's own state and
reports what it returns as findings; `gate` calls it with the state it gates. `change
verify`, `change finalize` and `change transition` all ask `gate`, so verify predicts what
finalize refuses because both evaluate one function, and a blocker carries the code of
the finding that reports the same rule.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from typing import TYPE_CHECKING

from irminsul.change.footprint import Footprint, touched_components
from irminsul.checks.base import Finding, Severity, sort_findings
from irminsul.checks.change_binding import CODE_MISSING_AFFECTS, CODE_UNKNOWN_COMPONENT
from irminsul.checks.claim_anchor import ClaimAnchorCheck
from irminsul.checks.pipeline import (
    RunResult,
    failing_findings,
    finish,
    run_check,
    run_checks,
    without_baselined,
)
from irminsul.checks.requirement_grammar import (
    RequirementGrammarCheck,
    requirement_grammar_findings,
    task_grammar_findings,
)
from irminsul.checks.rfc_follow_through import (
    CODE_MISSING_SECTION,
    CODE_UPDATE_MISSING_IMPLEMENTS,
    TERMINAL_SECTIONS,
    RfcFollowThroughCheck,
    has_heading,
)
from irminsul.checks.rfc_lifecycle import CODE_DANGLING_RESOLVED_BY
from irminsul.docgraph import DocGraph, DocNode
from irminsul.docgraph_index import slugify
from irminsul.frontmatter import RFC_COMMITTED_STATES, RfcStateEnum

if TYPE_CHECKING:
    from irminsul.change.report import ChangeBaseline

CODE_BASELINE_UNREADABLE = "baseline-unreadable"
CODE_MISSING_ADR = "missing-adr"
CODE_MISSING_REQUIREMENTS = "missing-requirements"
CODE_UNKNOWN_BASELINE = "unknown-baseline"
CODE_UNRECONCILED_SCOPE = "unreconciled-scope"
CODE_UNOWNED_CHANGE = "unowned-change"

#: The state `change status` and `change verify` judge an RFC against: the next one.
NEXT_STATE: dict[RfcStateEnum, RfcStateEnum] = {
    RfcStateEnum.draft: RfcStateEnum.accepted,
    RfcStateEnum.accepted: RfcStateEnum.implemented,
}


@dataclass(frozen=True)
class Issue:
    """One rule an RFC fails, worded once for the check and the gate that report it."""

    code: str
    message: str
    suggestion: str | None = None
    path: str | None = None

    @classmethod
    def of(cls, finding: Finding) -> Issue:
        return cls(
            code=finding.code,
            message=finding.message,
            suggestion=finding.suggestion,
            path=finding.path.as_posix() if finding.path else None,
        )


def missing_affects(rfc: DocNode, state: RfcStateEnum) -> Issue | None:
    if state not in RFC_COMMITTED_STATES or rfc.frontmatter.affects is not None:
        return None
    return Issue(
        CODE_MISSING_AFFECTS,
        f"{state.value} RFC does not declare `affects`; declare the component ids it "
        "changes, or `affects: []` for no owned source",
        "add `affects:` to the RFC frontmatter",
        rfc.path.as_posix(),
    )


def unknown_components(graph: DocGraph, rfc: DocNode) -> list[Issue]:
    return [
        Issue(
            CODE_UNKNOWN_COMPONENT,
            f"`affects` entry '{declared}' does not match any doc id in the graph",
            "correct the component id in `affects`",
            rfc.path.as_posix(),
        )
        for declared in rfc.frontmatter.affects or []
        if declared not in graph.nodes
    ]


def dangling_resolved_by(
    graph: DocGraph, rfc: DocNode, state: RfcStateEnum, resolved_by: str | None
) -> Issue | None:
    if state not in RFC_COMMITTED_STATES or resolved_by is None:
        return None
    if graph.doc_at(resolved_by) is not None:
        return None
    return Issue(
        CODE_DANGLING_RESOLVED_BY,
        f"resolved_by points to '{resolved_by}' but no such doc was found in the graph",
        "check the path; resolved_by is a repo-relative POSIX path to an existing decision doc",
        rfc.path.as_posix(),
    )


def missing_section(graph: DocGraph, rfc: DocNode, state: RfcStateEnum) -> Issue | None:
    """The scaffolding section a resolved RFC of `state` carries, when it has none of them."""
    sections = TERMINAL_SECTIONS.get(state)
    headings = graph.headings.get(rfc.id, [])
    if sections is None or any(has_heading(headings, slugify(title)) for title in sections):
        return None
    names = " or ".join(f"'## {title}'" for title in reversed(sections))
    return Issue(
        CODE_MISSING_SECTION,
        f"{state.value} RFC is missing a {names} section",
        "add the section summarising the outcome and linking the decision doc",
        rfc.path.as_posix(),
    )


def _resolution(
    graph: DocGraph, rfc: DocNode, state: RfcStateEnum, resolved_by: str | None
) -> Issue | None:
    if state in RFC_COMMITTED_STATES and not resolved_by:
        return Issue(
            CODE_MISSING_ADR,
            "an accepted RFC must resolve to a decision record; none is declared",
            "create it with `irminsul new adr <title>` and pass --resolved-by <adr path> to "
            "`change transition`",
            rfc.path.as_posix(),
        )
    return dangling_resolved_by(graph, rfc, state, resolved_by)


def requirement_findings(graph: DocGraph, rfc: DocNode) -> list[Finding]:
    """The requirements contract acceptance freezes: grammar findings, which warn while an RFC
    is drafted and block a transition."""
    section = graph.requirements.get(rfc.id)
    if section is None:
        return []
    found = requirement_grammar_findings(rfc, section, check_name=RequirementGrammarCheck.name)
    tasks_section = graph.tasks.get(rfc.id)
    if tasks_section is not None:
        found.extend(
            task_grammar_findings(
                rfc, tasks_section, section, check_name=RequirementGrammarCheck.name
            )
        )
    return found


def _no_requirements(graph: DocGraph, rfc: DocNode) -> Issue | None:
    if rfc.id in graph.requirements:
        return None
    return Issue(
        CODE_MISSING_REQUIREMENTS,
        "no `## Requirements` section: add requirement blocks or the explicit sentence "
        "'No new behavioral requirements: ...'",
        "each block is `### Requirement: <title>`, then `ID:`, `Provenance: "
        "code|adr|citation`, SHALL/MUST text, and `#### Scenario:` bullets with **WHEN** "
        "and **THEN**",
        rfc.path.as_posix(),
    )


@dataclass(frozen=True)
class GateRun:
    """The run of the enabled checks a lifecycle command blocks on, which is the run plain
    `irminsul check` makes; `blockers` holds what the run itself could not settle, a
    baseline file that does not load."""

    run: RunResult
    blockers: tuple[Issue, ...] = ()


def gate_run(graph: DocGraph) -> GateRun:
    """Run the enabled checks once, baseline applied, for a lifecycle command.

    Baselined adoption debt never blocks a transition, because it would not fail
    `irminsul check` either. A baseline that does not load is not read as no baseline,
    which would block on everything it records without saying why; it is a blocker of
    its own, and the same run, unbaselined, supplies the rest.
    """
    from irminsul.baseline import BaselineError

    assert graph.config is not None
    run = run_checks(graph, baseline=False)
    try:
        return GateRun(run.with_baseline(graph))
    except BaselineError as exc:
        return GateRun(
            run,
            (
                Issue(
                    CODE_BASELINE_UNREADABLE,
                    str(exc),
                    "restore the baseline file from git; `irminsul check` refuses it as well",
                    graph.config.paths.baseline,
                ),
            ),
        )


_Key = tuple[str, str | None, str]


def _key(item: Issue | Finding) -> _Key:
    issue = Issue.of(item) if isinstance(item, Finding) else item
    return issue.code, issue.path, issue.message


@dataclass(frozen=True)
class Gate:
    """What moving one RFC to a target state is blocked on, and what its rules read."""

    issues: tuple[Issue, ...]
    footprint: Footprint | None = None
    """Where the range's changed paths landed; None without a resolved range."""
    run: RunResult | None = None
    judged: frozenset[_Key] = frozenset()
    """Every issue a rule here evaluated, raised or not, including the check's own copy."""
    anchor_scope: frozenset[str] = frozenset()

    def covers(self, finding: Finding) -> bool:
        """Whether a rule here judged `finding` itself, so the enabled checks' copy is
        neither a second blocker nor a scoped finding."""
        return _covered(finding, self.judged, self.anchor_scope)


def _covered(finding: Finding, judged: frozenset[_Key], anchor_scope: frozenset[str]) -> bool:
    path = finding.path.as_posix() if finding.path else None
    if finding.check == ClaimAnchorCheck.name and path in anchor_scope:
        return finding.severity in (Severity.warning, Severity.error)
    return _key(finding) in judged


def gate(
    graph: DocGraph,
    rfc: DocNode,
    target: RfcStateEnum | None,
    baseline: ChangeBaseline | None,
    *,
    checks: bool = True,
    resolved_by: str | None = None,
) -> Gate:
    """What `rfc` is blocked on to enter `target`, judged over `baseline`.

    Only `accepted` and `implemented` have rules of their own. Acceptance does not ask for
    the terminal section, because the transition writes it. A `target` of None judges the
    RFC's declarations at its own state, as a report on a finished RFC does. `baseline` is
    the implementation range, or None for a caller that judges none. `checks` adds the errors
    of the enabled checks that no rule here already judged. `resolved_by` stands in for the
    RFC's own, for a transition that records one.
    """
    fm = rfc.frontmatter
    own = fm.rfc_state
    assert own is not None
    judged: set[_Key] = set()

    def judge(raised: Iterable[Issue | None], *checked: Issue | Finding | None) -> list[Issue]:
        issues = [issue for issue in raised if issue is not None]
        judged.update(_key(item) for item in (*issues, *checked) if item is not None)
        return issues

    shape: list[Issue] = []
    contract: list[Issue] = []
    finishing: list[Issue] = []
    scope: frozenset[str] = frozenset()
    if target in RFC_COMMITTED_STATES:
        resolved = resolved_by if resolved_by is not None else fm.resolved_by
        shape += judge([missing_affects(rfc, target)], missing_affects(rfc, own))
        shape += judge(unknown_components(graph, rfc))
        shape += judge(
            [_resolution(graph, rfc, target, resolved)],
            dangling_resolved_by(graph, rfc, own, fm.resolved_by),
        )
        grammar = requirement_findings(graph, rfc)
        contract = judge([_no_requirements(graph, rfc), *map(Issue.of, grammar)])
        if target == RfcStateEnum.implemented:
            shape += judge([missing_section(graph, rfc, target)], missing_section(graph, rfc, own))
            updates = _required_updates(graph, rfc)
            finishing += judge(
                [Issue.of(f) for f in updates if f.code != CODE_UPDATE_MISSING_IMPLEMENTS],
                *updates,
            )
            scope, anchors = _anchors(graph, rfc)
            finishing += anchors
    elif target is None:
        shape += judge([missing_affects(rfc, own)])
        shape += judge(unknown_components(graph, rfc))
        shape += judge([dangling_resolved_by(graph, rfc, own, fm.resolved_by)])

    footprint: Footprint | None = None
    unmeasured: list[Issue] = []
    if baseline is not None and baseline.changed_paths is None:
        unmeasured.append(
            Issue(
                CODE_UNKNOWN_BASELINE,
                "no diff baseline could be resolved, so no implementation evidence can be derived",
                "pass --base-ref <ref>, set IRMINSUL_BASE_REF, or run from a git worktree",
                rfc.path.as_posix(),
            )
        )
    elif baseline is not None and baseline.changed_paths is not None:
        footprint = touched_components(graph, frozenset(baseline.changed_paths))
        if target == RfcStateEnum.implemented:
            finishing += _scope(rfc, footprint)

    gated = gate_run(graph) if checks else None
    run = gated.run if gated else None
    seen = frozenset(judged)
    errors = [
        Issue.of(finding)
        for finding in sort_findings(failing_findings(run.findings if run else []))
        if not _covered(finding, seen, scope)
    ]
    blockers = gated.blockers if gated else ()
    issues = (*blockers, *shape, *errors, *contract, *unmeasured, *finishing)
    return Gate(issues, footprint, run, seen, scope)


def step_gate(
    graph: DocGraph,
    rfc: DocNode,
    target: RfcStateEnum,
    baseline: ChangeBaseline | None,
    *,
    resolved_by: str | None = None,
) -> Gate:
    """What the lifecycle step into `target` blocks on. A person's decision, `accepted` or
    `rejected`, judges the RFC alone; finalization also judges the range and the enabled
    checks."""
    finalizes = target == RfcStateEnum.implemented
    return gate(
        graph,
        rfc,
        target,
        baseline if finalizes else None,
        checks=finalizes,
        resolved_by=resolved_by,
    )


def _required_updates(graph: DocGraph, rfc: DocNode) -> list[Finding]:
    """This RFC's required-update findings as they stand once it is implemented, whether or
    not `rfc-follow-through` is enabled, through ignore comments and the baseline. A doc
    the RFC creates has to exist by then.

    An `update-missing-implements` is judged but never raised: adding that `implements`
    entry is the write finalization makes, and blocking on it would make that write
    unreachable.
    """
    found = RfcFollowThroughCheck().required_update_findings(graph, rfc, as_implemented=True)
    return without_baselined(graph, finish(found, graph))


def declared_docs(graph: DocGraph, rfc: DocNode) -> frozenset[str]:
    """The RFC and the component docs its `affects` names, as repo-relative paths."""
    owners = (graph.nodes.get(component) for component in rfc.frontmatter.affects or ())
    return frozenset({rfc.path.as_posix(), *(o.path.as_posix() for o in owners if o)})


def _anchors(graph: DocGraph, rfc: DocNode) -> tuple[frozenset[str], list[Issue]]:
    """Anchors in the RFC and the component docs it declares, which must resolve and be fresh
    before finalization whether or not `claim-anchor` is enabled."""
    scope = declared_docs(graph, rfc)
    found = [
        Issue.of(finding)
        for finding in sort_findings(run_check(ClaimAnchorCheck, graph))
        if finding.severity in (Severity.warning, Severity.error)
        and (finding.path.as_posix() if finding.path else None) in scope
    ]
    return scope, found


def _scope(rfc: DocNode, footprint: Footprint) -> list[Issue]:
    """Changed source belongs to a component the RFC declares: one `affects` leaves out is
    unreconciled, and source no component claims is unowned."""
    out: list[Issue] = []
    undeclared = sorted(set(footprint.touched) - set(rfc.frontmatter.affects or []))
    if undeclared:
        out.append(
            Issue(
                CODE_UNRECONCILED_SCOPE,
                "the change touches component(s) this RFC's `affects` does not declare: "
                f"{', '.join(undeclared)}",
                "add them to `affects` if the RFC covers them, or move that work out of this change",
                rfc.path.as_posix(),
            )
        )
    out.extend(
        Issue(
            CODE_UNOWNED_CHANGE,
            f"changed source '{unowned}' has no component claim",
            "extend a component doc's `describes` (curated, not automatic)",
            unowned,
        )
        for unowned in footprint.unowned_source
    )
    return out
