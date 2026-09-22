"""The shared path a check's findings take before any command reports them.

A check chooses a severity for each finding; its code's class has the last word. A
certain finding is an error, unless it sits on a draft doc *and* its code is one the
check declares in `drafts_exempt` — a code reporting that the doc is unfinished rather
than that it is wrong about something outside it. A hint or time finding is never an
error. Given a diff range, time findings are left
out, because a change cannot have caused them. Then a doc's ignore comments drop the
hint and time findings they cover.

Two classes, named apart because they answer different questions:

- `class_of(code)` is what the **code** declares. It is fixed for the code, so it is
  what `explain` prints and what decides whether an ignore comment naming that code is
  allowed at all — a comment names a code, and cannot depend on the status of whichever
  doc it lands in.
- `effective_class(finding)` is what **this occurrence** enforces as, and the exit code
  follows it. The draft exemption is the only thing that separates the two: it demotes a
  certain finding to a warning, and a warning enforces as a hint.

So a demoted finding reports `class: certain` and `effective_class: hint`, is not
silenceable by a comment, and fails under `--strict` or `--fail-on hint` but not under
the default run. `severity` is the same fact in the older vocabulary: error exactly when
the effective class is certain.
"""

from __future__ import annotations

from collections.abc import Callable, Collection
from contextlib import suppress
from dataclasses import replace
from functools import cache
from typing import Final

from irminsul.checks.base import Check, Finding, FindingClass, Severity
from irminsul.docgraph import DocGraph
from irminsul.frontmatter import StatusEnum


@cache
def _all_checks() -> tuple[type[Check], ...]:
    from irminsul.checks import REGISTRY
    from irminsul.checks.adoption_record import AdoptionRecordCheck
    from irminsul.checks.co_change import CoChangeCheck
    from irminsul.checks.diff_integrity import DiffIntegrityCheck
    from irminsul.checks.history_depth import HistoryDepthCheck
    from irminsul.checks.ignore_comments import IgnoreCommentCheck
    from irminsul.checks.new_dependency import NewDependencyCheck

    return (
        *REGISTRY.values(),
        AdoptionRecordCheck,
        CoChangeCheck,
        DiffIntegrityCheck,
        HistoryDepthCheck,
        IgnoreCommentCheck,
        NewDependencyCheck,
    )


@cache
def _classes() -> dict[str, FindingClass]:
    out: dict[str, FindingClass] = {}
    for cls in _all_checks():
        out.update(cls.classes)
    return out


@cache
def _drafts_exempt() -> frozenset[str]:
    return frozenset().union(*(getattr(cls, "drafts_exempt", frozenset()) for cls in _all_checks()))


@cache
def audits_suppression() -> frozenset[str]:
    """Codes that report on a suppression marker, declared by the checks themselves.

    A baseline must not hide one, and keeping that list in `baseline.py` meant a new
    such code was silently baselinable — which is how an unclosed `ignore-start`, a
    marker that silences the rest of a doc, became hideable.
    """
    return frozenset().union(
        *(getattr(cls, "audits_suppression", frozenset()) for cls in _all_checks())
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

    An *error* whose code no check declares still enforces as certain. Every code in the
    tree is classed today, so this is latent, but the direction matters: a code left out
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
    """Run one check through classes and ignore comments."""
    from irminsul.checks.ignore_comments import apply_ignore_comments

    return apply_ignore_comments(apply_classes(cls().run(graph), graph), graph)


def finish(
    findings: list[Finding],
    graph: DocGraph,
    *,
    ran: Collection[str] | None = None,
    diff: bool = False,
) -> list[Finding]:
    """Classes and ignore comments for findings gathered from several checks."""
    from irminsul.checks.ignore_comments import apply_ignore_comments

    classified = apply_classes(findings, graph)
    return apply_classes(apply_ignore_comments(classified, graph, ran=ran), graph, diff=diff)


def _adoption_record_pass(graph: DocGraph, selected: Collection[str]) -> list[Finding]:
    from irminsul.checks.adoption_record import run_adoption_record

    return run_adoption_record(graph, selected)


def _history_depth_pass(graph: DocGraph, selected: Collection[str]) -> list[Finding]:
    from irminsul.checks.history_depth import run_history_depth

    if graph.repo_root is None:
        return []
    return run_history_depth(graph.repo_root, selected)


#: Passes no run may omit, whatever `checks.enabled` says and whoever assembled the run.
#: Data rather than a sequence of calls, so a test can replace each one with a sentinel and
#: prove every entry point fired it — the shape of the bug this exists to close, where four
#: callers each built their own idea of what a run consists of.
MANDATORY_PASSES: Final[tuple[Callable[[DocGraph, Collection[str]], list[Finding]], ...]] = (
    _adoption_record_pass,
    _history_depth_pass,
)


def mandatory_findings(graph: DocGraph, selected: Collection[str]) -> list[Finding]:
    """The passes that judge the run rather than the graph, for any caller running checks.

    **A check may delegate error reporting only where the calling execution path guarantees
    that the responsible validation runs.** That is the contract this function exists to
    keep, and it is not a style preference. `uniqueness` and `test-ownership` swallow
    `AdoptionError` on purpose, because the `adoption-record` pass reports it — so a caller
    that runs those two without this is a caller for which an unreadable adoption record is
    a tree with no debt and no problem. `mcp_server.check_json` and `context` were both such
    callers, and both reported a clean repository over a finding that blocks.

    Neither pass is in `REGISTRY`, because `checks.enabled` is a list a repository writes and
    neither of these is a check a repository may decline. That is only true while every
    entry point comes through here, which is what `MANDATORY_PASSES` lets a test assert.

    Findings come back unclassified: the caller passes them through `finish` with whatever
    diff state its run has, because a `time` finding's fate depends on that and this does not
    know it.
    """
    out: list[Finding] = []
    for run in MANDATORY_PASSES:
        out.extend(run(graph, selected))
    return out


def enabled_findings(graph: DocGraph, *, baseline: bool = True) -> list[Finding]:
    """What `irminsul check` reports for the enabled checks, after the baseline.

    Lifecycle gates block on these errors, so a transition is refused for exactly what
    would fail the repository's own check, and adoption debt a baseline records does
    not block it forever.
    """
    from irminsul.checks import REGISTRY

    if graph.config is None:
        return []
    names = [name for name in graph.config.checks.enabled if name in REGISTRY]
    findings: list[Finding] = []
    for name in names:
        findings.extend(REGISTRY[name]().run(graph))
    findings.extend(mandatory_findings(graph, names))
    findings = finish(findings, graph, ran=names)
    return without_baselined(graph, findings) if baseline else findings


def without_baselined(graph: DocGraph, findings: list[Finding]) -> list[Finding]:
    """`findings` without those the repository's baseline records."""
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
