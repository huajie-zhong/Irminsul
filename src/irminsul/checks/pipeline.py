"""The shared path a check's findings take before any command reports them.

First a doc's ignore comments drop the hint and time findings they cover; which ones a
comment may drop is decided by the class a code declares, so nothing about severity
has to be settled first. Then classes: a check chooses a severity for each finding, and
its code's class has the last word. A certain finding is an error, unless it sits on a
draft doc *and* its code is one the check declares in `drafts_exempt` — a code reporting
that the doc is unfinished rather than that it is wrong about something outside it. A
hint or time finding is never an error. Given a diff range, time findings are left out,
because a change cannot have caused them.

Two classes, named apart because they answer different questions:

- `class_of(code)` is what the **code** declares. It is fixed for the code, so it is
  what `explain` prints and what decides whether an ignore comment naming that code is
  allowed at all — a comment names a code, and cannot depend on the status of whichever
  doc it lands in.
- `effective_class(finding)` is what **this occurrence** enforces as, and the exit code
  follows it. The draft exemption is the only thing that separates the two: it demotes a
  certain finding to a warning, and a warning enforces as a hint.

So a demoted finding reports `class: certain` and `effective_class: hint`, is not
silenceable by a comment, and fails under `--fail-on hint` but not under
the default run. `severity` is the same fact in the older vocabulary: error exactly when
the effective class is certain.
"""

from __future__ import annotations

import difflib
from collections.abc import Collection, Iterable
from contextlib import suppress
from dataclasses import dataclass, field, replace
from functools import cache
from typing import TYPE_CHECKING, Final

from irminsul.checks import REGISTRY
from irminsul.checks.adoption_record import AdoptionRecordPass
from irminsul.checks.base import (
    Answer,
    Check,
    Finding,
    FindingClass,
    FindingSource,
    Pass,
    Severity,
    sort_findings,
)
from irminsul.checks.co_change import CoChangePass
from irminsul.checks.diff_integrity import DiffIntegrityPass
from irminsul.checks.history_depth import HistoryDepthPass
from irminsul.checks.ignore_comments import IgnoreCommentFilter
from irminsul.checks.new_dependency import NewDependencyPass
from irminsul.config import IrminsulConfig
from irminsul.docgraph import DocGraph
from irminsul.errors import UserError
from irminsul.frontmatter import StatusEnum

if TYPE_CHECKING:
    from irminsul.delta import DeltaResult

#: Passes no run may omit, whatever `checks.enabled` says and whoever assembled the run.
#: Every run calls every one, in this order after the registered checks, so a test can
#: replace each with a sentinel and prove every entry point fired it.
PASSES: Final[dict[str, type[Pass]]] = {
    cls.name: cls
    for cls in (
        AdoptionRecordPass,
        HistoryDepthPass,
        CoChangePass,
        DiffIntegrityPass,
        NewDependencyPass,
    )
}


#: The passes that judge a change rather than the tree: each reads `graph.change` and reports
#: nothing for a graph with no range, so a run given no base has not run them. Named through
#: their classes, so a rename follows.
CHANGE_PASSES: Final = tuple(
    cls.name for cls in (CoChangePass, DiffIntegrityPass, NewDependencyPass)
)


@cache
def finding_sources() -> dict[str, type[FindingSource]]:
    """Everything that emits findings under a name: the registered checks, the passes, and
    the ignore-comment filter. The one place that knows all of them, so a new one is
    explainable, classed, and nameable in an ignore comment without a second list."""
    return {
        **REGISTRY,
        **PASSES,
        IgnoreCommentFilter.name: IgnoreCommentFilter,
    }


@cache
def _classes() -> dict[str, FindingClass]:
    out: dict[str, FindingClass] = {}
    for cls in finding_sources().values():
        out.update(cls.classes)
    return out


@cache
def _answers() -> dict[str, Answer]:
    out: dict[str, Answer] = {}
    for cls in finding_sources().values():
        out.update(getattr(cls, "answers", {}))
    return out


_FIX: Final = Answer.fix("")


def answer_of(code: str) -> Answer:
    """The answer a code declares. A test holds every hint and time code to one, so a code
    that declares none is certain and answered by the fix its explanation gives."""
    return _answers().get(code, _FIX)


@cache
def _drafts_exempt() -> frozenset[str]:
    return frozenset().union(
        *(getattr(cls, "drafts_exempt", frozenset()) for cls in finding_sources().values())
    )


@cache
def audits_suppression() -> frozenset[str]:
    """Codes that report on a suppression marker, declared by the checks themselves.

    A baseline must not hide one, and a list kept in `baseline.py` would leave a new
    such code silently baselinable — an unclosed `ignore-start`, a marker that silences
    the rest of a doc, would be hideable.
    """
    return frozenset().union(
        *(getattr(cls, "audits_suppression", frozenset()) for cls in finding_sources().values())
    )


def class_of(code: str) -> FindingClass | None:
    """The class a *code* declares — a property of the message template, not of one
    occurrence of it. `irminsul explain` prints this, and an ignore comment names a
    code, so suppression eligibility reads this."""
    return _classes().get(code)


def effective_class(finding: Finding) -> FindingClass | None:
    """The class *this occurrence* enforces as, which the run's exit code follows.

    It differs from the declared class in exactly one situation: the draft exemption
    demoted a certain finding to a warning, and a warning enforces as a hint
    everywhere else, so it enforces as one here too. `None` means no flag fails on it
    — an info finding, or a code no check declares.

    An *error* whose code no check declares still enforces as certain. A test holds every
    explained code to a class, so this is latent, but the direction matters: a code left out
    of its check's `classes` map is a mistake, and the failure mode for a mistake here has
    to be a run that fails loudly rather than one that prints a red error and exits 0.
    """
    declared = class_of(finding.code)
    if declared is None:
        return FindingClass.certain if finding.severity is Severity.error else None
    if finding.severity is Severity.info:
        return None
    if declared is FindingClass.certain and finding.severity is not Severity.error:
        return FindingClass.hint
    return declared


def apply_classes(findings: list[Finding], graph: DocGraph, *, diff: bool = False) -> list[Finding]:
    out: list[Finding] = []
    for finding in findings:
        finding_class = class_of(finding.code)
        if finding_class is FindingClass.certain:
            draft_exempt = finding.code in _drafts_exempt() and _on_draft(finding, graph)
            severity = Severity.warning if draft_exempt else Severity.error
            if finding.severity is not severity:
                finding = replace(finding, severity=severity)
        elif finding_class is not None:
            if diff and finding_class is FindingClass.time:
                continue
            if finding.severity is Severity.error:
                finding = replace(finding, severity=Severity.warning)
        out.append(finding)
    return out


def is_time(finding: Finding) -> bool:
    return class_of(finding.code) is FindingClass.time


def run_check(cls: type[Check], graph: DocGraph) -> list[Finding]:
    """One check's findings through `finish`, for a view that reports that check's own
    items. It reaches no verdict, so it audits no ignore comment and applies no baseline;
    a verdict is `run_checks`."""
    return finish(cls().run(graph), graph)


def finish(
    findings: list[Finding],
    graph: DocGraph,
    *,
    ran: Collection[str] | None = None,
    diff: bool = False,
) -> list[Finding]:
    """Ignore comments, then classes — the path every finding takes before it is reported.

    Ignore comments go first because which findings a comment may silence is decided by
    the class a code declares, never by the severity a check chose, so classifying first
    would change nothing. `ran` names the registered checks whose findings these are and
    turns on the audit of misused comments; `diff` leaves out time findings.
    """
    from irminsul.checks.ignore_comments import apply_ignore_comments

    return apply_classes(apply_ignore_comments(findings, graph, ran=ran), graph, diff=diff)


def pass_findings(graph: DocGraph, selected: Collection[str]) -> list[Finding]:
    """What the passes report for a run making the checks `selected`.

    **A check may delegate error reporting only where the calling execution path guarantees
    that the responsible validation runs.** That is the contract this function exists to
    keep, and it is not a style preference. `uniqueness` and `test-ownership` swallow
    `AdoptionError` on purpose, because the `adoption-record` pass reports it — so a caller
    that runs those two without this is a caller for which an unreadable adoption record is
    a tree with no debt and no problem.

    No pass is in `REGISTRY`, because `checks.enabled` is a list a repository writes and
    none of these is a check a repository may decline. That is only true while every entry
    point comes through here, which is what `PASSES` lets a test assert.

    Findings come back unclassified: the caller passes them through `finish` with whatever
    diff state its run has, because a `time` finding's fate depends on that and this does not
    know it.
    """
    out: list[Finding] = []
    for cls in PASSES.values():
        out.extend(cls().run(graph, selected))
    return out


@dataclass(frozen=True)
class BaselineStatus:
    """Whether the repository's baseline file was applied to a run, and how much of it is
    stale — entries that matched nothing in a run that could have matched them, which
    `irminsul baseline update` removes."""

    applied: bool = False
    path: str | None = None
    stale: int = 0


@dataclass(frozen=True)
class RunResult:
    """One run of the checks, after classes, ignore comments, and the baseline.

    `findings` is what the run reports and `hidden` what the baseline hid from it, so a
    caller that needs the run as if no baseline existed — `baseline init`, `list
    baseline`, the delta comparison — reads both from the same run rather than running
    the checks again.
    """

    findings: list[Finding]
    hidden: list[Finding] = field(default_factory=list)
    ran: tuple[str, ...] = ()
    baseline_status: BaselineStatus = field(default_factory=BaselineStatus)

    @property
    def unbaselined(self) -> list[Finding]:
        return sort_findings([*self.findings, *self.hidden])

    def failing(self, fail_on: Collection[FindingClass] = ()) -> list[Finding]:
        """The reported findings that fail the run: every one whose effective class is
        certain, and those of the classes `fail_on` adds. No argument narrows the set."""
        return failing_findings(self.findings, fail_on)

    def failed(self, fail_on: Collection[FindingClass] = ()) -> bool:
        return bool(self.failing(fail_on))

    def baseline_report(self) -> dict[str, object]:
        """The `baseline` object every JSON surface carries."""
        status = self.baseline_status
        return {
            "applied": status.applied,
            "path": status.path,
            "suppressed": len(self.hidden),
            "stale": status.stale,
            "hidden": [
                {
                    "check": f.check,
                    "code": f.code,
                    "path": f.path.as_posix() if f.path else None,
                    "message": f.message,
                }
                for f in self.hidden
            ],
        }

    def with_baseline(self, graph: DocGraph) -> RunResult:
        """This run with the repository's baseline file applied, as a step after the run.

        What the file records moves from `findings` to `hidden`. A file that does not load
        raises `BaselineError`, and the run it was asked of is still the caller's to use,
        so nobody has to run the checks again to go on without it.
        """
        from irminsul.baseline import apply_baseline, load_entries

        if self.baseline_status.applied or graph.config is None or graph.repo_root is None:
            return self
        path = graph.config.paths.baseline
        baseline_file = graph.repo_root / path
        if not baseline_file.is_file():
            return self
        # An entry of an enabled check that `--only` left out of this run could not have
        # matched, so it is not fixed. One no run could match, such as a disabled check's or
        # a pass's, is fixed in any run, as `baseline update` and `list baseline` read it.
        left_out = set(graph.config.checks.enabled) - set(self.ran)
        recorded = [e for e in load_entries(baseline_file) if e.check not in left_out]
        application = apply_baseline(self.findings, {entry.fingerprint for entry in recorded})
        return replace(
            self,
            findings=application.remaining,
            hidden=application.hidden,
            baseline_status=BaselineStatus(applied=True, path=path, stale=application.stale),
        )


def run_delta(working: RunResult, graph: DocGraph, rev: str, *, remedy: str) -> DeltaResult:
    """What `working`, the run made over `graph`, reports that the same run at `rev` does not.

    `rev` is checked out into a scratch worktree and given the same run: the checks
    `working` ran, the mandatory passes, and `graph`'s `now`, all read from the working
    side so no caller can hand the base a different run. Two things differ, both on purpose.
    The base graph gets no diff range, because the passes that read one judge the change,
    so what they report is never pre-existing. And neither side is baselined: a baseline
    says what to hide, not what existed, so `working` is compared whole. The base graph
    also reads commits alone: its scratch checkout holds no uncommitted work to count.

    Raises `DeltaError` when no comparison can be trusted: a configured tree in another
    repository, which the checkout would omit; a base that is the working tree, where
    every finding would be pre-existing and the zero would measure nothing
    (`UnchangedTreeError`, which ends with `remedy`, the step the caller's flags offer); or
    a checkout that fails.
    """
    from irminsul.delta import (
        UnchangedTreeError,
        base_is_the_working_tree,
        compute_delta,
        pristine_checkout,
        verify_single_repo_topology,
    )
    from irminsul.docgraph import build_graph

    repo_root, config = graph.repo_root, graph.config
    if repo_root is None or config is None:
        raise ValueError("a DocGraph with no repo root or config has no base to compare")
    # The topology refusal comes first: it says this repository shape cannot be compared
    # at all, which outranks having nothing to compare in this run.
    verify_single_repo_topology(repo_root, config)
    if base_is_the_working_tree(repo_root, config, rev):
        raise UnchangedTreeError(rev, remedy)
    with pristine_checkout(repo_root, rev) as base_root:
        # The scratch worktree is deleted on teardown; run-spanning check state (the
        # external-links cache) belongs in the caller's repository.
        base_graph = build_graph(
            base_root, config, now=graph.now, state_root=repo_root, committed_only=True
        )
        base = run_checks(base_graph, only=working.ran, baseline=False)
    return compute_delta(working.unbaselined, base.findings)


def failing_findings(
    findings: list[Finding], fail_on: Collection[FindingClass] = ()
) -> list[Finding]:
    failing = {FindingClass.certain, *fail_on}
    return [finding for finding in findings if effective_class(finding) in failing]


def run_checks(
    graph: DocGraph, *, only: Collection[str] | None = None, baseline: bool = True
) -> RunResult:
    """The whole run every verdict is reached from."""
    if graph.config is None:
        raise ValueError("a DocGraph with no config has no checks to run")
    names = select_checks(graph.config, only)
    raw: list[Finding] = []
    for name in names:
        raw.extend(REGISTRY[name]().run(graph))
    raw.extend(pass_findings(graph, names))
    findings = sort_findings(finish(raw, graph, ran=names, diff=graph.change is not None))
    result = RunResult(findings, ran=tuple(names))
    return result.with_baseline(graph) if baseline else result


def describe_unknown_checks(names: Collection[str]) -> str:
    """Each name, with the registered check it most resembles, for an error message."""
    return ", ".join(f"'{name}'{did_you_mean(name, REGISTRY)}" for name in names)


def did_you_mean(name: str, choices: Iterable[str], *, limit: int = 1) -> str:
    """` (did you mean 'x'?)` for the `limit` closest of `choices`, or "" when none is close."""
    matches = difflib.get_close_matches(name, list(choices), n=limit)
    if not matches:
        return ""
    quoted = " or ".join(f"'{match}'" for match in matches)
    return f" (did you mean {quoted}?)"


class UnknownCheckError(UserError, ValueError):
    """`only` named a check that is not registered."""


def select_checks(config: IrminsulConfig, only: Collection[str] | None = None) -> list[str]:
    """The checks a run executes: `only`, enabled or not, or else `checks.enabled`.

    An unregistered name raises `UnknownCheckError`: a selector that matches nothing runs
    nothing, and a run that checked nothing passes.
    """
    if not only:
        return [name for name in config.checks.enabled if name in REGISTRY]
    unknown = [name for name in only if name not in REGISTRY]
    if unknown:
        raise UnknownCheckError(f"unknown check name(s): {describe_unknown_checks(unknown)}")
    return list(dict.fromkeys(only))


def without_baselined(graph: DocGraph, findings: list[Finding]) -> list[Finding]:
    """`findings` without those the repository's baseline records.

    A baseline that does not load hides nothing here: the caller's own run reports it,
    as the lifecycle gates do with a blocker, so this is never its only reader.
    """
    from irminsul.baseline import BaselineError, apply_baseline, load_baseline

    if graph.config is None or graph.repo_root is None:
        return findings
    baseline_file = graph.repo_root / graph.config.paths.baseline
    if baseline_file.is_file():
        with suppress(BaselineError):
            return apply_baseline(findings, load_baseline(baseline_file)).remaining
    return findings


def _on_draft(finding: Finding, graph: DocGraph) -> bool:
    node = graph.nodes.get(finding.doc_id) if finding.doc_id else None
    if node is None and finding.path is not None:
        node = graph.by_path.get(finding.path)
    return node is not None and node.frontmatter.status == StatusEnum.draft
