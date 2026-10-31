"""The acknowledgement step: an `Irminsul-Reviewed` commit trailer signs off one finding.

A finding whose code declares `trailer` says something a reader can re-read and still find
right, such as a doc that did not change with the code it claims. A trailer on a commit of the
change names the finding by code, path and subject and gives a reason. The step accepts the
finding at info under its own code, quoting the reason. A trailer covers the changes made up
to its own commit, so a later change to a file the finding is about lapses it.
"""

from __future__ import annotations

import re
from collections.abc import Collection, Iterable
from dataclasses import dataclass, replace
from pathlib import Path
from typing import TYPE_CHECKING, ClassVar, Final

from irminsul.checks.base import Answer, AnswerKind, Finding, FindingClass, Severity
from irminsul.docgraph import ChangeRange, DocGraph, _spelled_from_root

if TYPE_CHECKING:
    from irminsul.git.reader import GitReader

CHECK_NAME: Final = "acknowledgement"
CODE_INVALID: Final = "acknowledgement/invalid"
CODE_UNUSED: Final = "acknowledgement/unused"
TRAILER_KEY: Final = "Irminsul-Reviewed"
ACKNOWLEDGED_IN: Final = "acknowledged_in"
REASON: Final = "reason"
TRAILER_RULE: Final = (
    "A trailer covers the changes made up to its own commit, so a later change to the files "
    "the finding is about needs a later trailer, and a change not yet committed is later than "
    "every commit. A finding's suggestion prints its exact trailer; the subject is left out "
    "only where it would repeat the path."
)

_TRAILER_RE = re.compile(
    r"(?P<code>\S+)"
    r'(?:\s+(?!reason=)(?P<path>[^\s"]+))?'
    r'(?:\s+(?!reason=)(?P<subject>[^\s"]+))?'
    r'(?:\s+reason="(?P<reason>[^"]*)")?\s*'
)

REASON_PLACEHOLDER: Final = "..."
"""What `trailer_for` and `trailer_form` print in place of a reason. Left unedited it gives none."""

_UNUSED_SUGGESTION: Final = (
    "nothing to do unless it names the wrong path or subject; then add a trailer naming the "
    "right one to a later commit"
)


@dataclass(frozen=True)
class Trailer:
    """One `Irminsul-Reviewed` trailer read from a commit in the diff range."""

    commit: str
    value: str
    changed_after: frozenset[str]
    """What the range changes in commits after this one, which its writer cannot have
    re-read the finding's files against."""


@dataclass(frozen=True)
class _Parsed:
    code: str
    path: str
    subject: str | None
    reason: str


@dataclass(frozen=True)
class _Named:
    """A trailer read down to the finding it names."""

    trailer: Trailer
    code: str
    path: str
    subject: str
    reason: str


@dataclass(frozen=True)
class _Problem:
    problem: str
    suggestion: str


class AcknowledgementStep:
    """The one step that lets a trailer of the change accept a finding.

    Neither a check nor a pass: it reads the change's trailers and works on the findings the
    others produced, through `apply_acknowledgements`, so it declares its codes and has
    nothing to run.
    """

    name: ClassVar[str] = CHECK_NAME
    default_severity: ClassVar[Severity] = Severity.info
    explanations: ClassVar[dict[str, str]] = {
        CODE_INVALID: (
            f"An `{TRAILER_KEY}` commit trailer that cannot acknowledge a finding: it does not "
            "parse, names no path or gives no reason, or names a code that is not declared "
            "`trailer`. It is info, because a commit trailer cannot be removed without rewriting "
            "history; a later commit carries a valid one."
        ),
        CODE_UNUSED: (
            f"An `{TRAILER_KEY}` commit trailer that matches no finding in this change, so it "
            "does nothing. Nothing is left to do unless it names the wrong path or subject; "
            "then a trailer naming the right one on a later commit answers it. When a finding "
            "on the same path and subject carries another code that declares `trailer`, the "
            "message names that code, and a trailer naming that code on a later commit answers "
            "that finding, if it is acceptable. It is info for the same reason as the invalid one."
        ),
    }
    classes: ClassVar[dict[str, FindingClass]] = {
        CODE_INVALID: FindingClass.hint,
        CODE_UNUSED: FindingClass.hint,
    }
    answers: ClassVar[dict[str, Answer]] = {
        CODE_INVALID: Answer.fix("add a valid trailer to a later commit"),
        CODE_UNUSED: Answer.fix("nothing to do: the trailer lapses when this change merges"),
    }


def parse(value: str) -> _Parsed | str:
    """What a trailer names, or the problem with its wording."""
    match = _TRAILER_RE.fullmatch(value)
    if match is None:
        return "is not written as a code, a path and a reason"
    if match["path"] is None:
        return "names no path"
    reason = (match["reason"] or "").strip()
    if not reason or reason == REASON_PLACEHOLDER:
        return "gives no reason"
    return _Parsed(match["code"], match["path"], match["subject"], reason)


def acknowledge(
    findings: list[Finding],
    trailers: list[Trailer],
    graph: DocGraph,
    *,
    ran: Collection[str] | None,
) -> list[Finding]:
    """`findings` with each one the trailers accept reported at info, plus the trailers that
    misuse the step or match nothing.

    A trailer accepts a finding whose code, path and subject it names, and only a code
    declared `trailer`. A later change to a file the finding is about lapses the trailer, and
    a lapsed trailer is named on the finding's suggestion. Misuse and unused trailers are
    reported only when `ran` names the checks the run made.
    """
    named: list[_Named] = []
    problems: list[Finding] = []
    for trailer in trailers:
        read = _read(trailer, graph)
        if isinstance(read, _Problem):
            if ran is not None:
                problems.append(_invalid(trailer, read))
        else:
            named.append(read)

    used: set[int] = set()
    out: list[Finding] = []
    for finding in findings:
        hits = [index for index, read in enumerate(named) if _matches(finding, read)]
        used.update(hits)
        if hits:
            finding = _judge(finding, [named[index] for index in hits], graph)
        out.append(finding)
    if ran is not None:
        out.extend(_unused(read, findings) for index, read in enumerate(named) if index not in used)
    return out + problems


def accepted(finding: Finding) -> bool:
    """Whether the acknowledgement step accepted `finding`, so it is already signed off."""
    return finding.data is not None and ACKNOWLEDGED_IN in finding.data


def about_of(finding: Finding) -> tuple[str, ...]:
    if finding.about:
        return finding.about
    return (finding.path.as_posix(),) if finding.path is not None else ()


def shown_path(path: str, uncommitted: frozenset[str]) -> str:
    return f"{path} (uncommitted)" if path in uncommitted else path


def placement(finding: Finding, uncommitted: frozenset[str]) -> str:
    """Where the trailer goes: on the commit that carries uncommitted work, or else on the
    commit that carries the last change to what the finding is about, or a later one."""
    about = about_of(finding)
    pending = [path for path in about if path in uncommitted]
    if pending:
        return f"in the message of the commit that carries {', '.join(pending)}"
    return f"on the commit that carries the last change to {', '.join(about)}, or a later one"


def trailer_for(finding: Finding) -> str:
    """The trailer that acknowledges `finding`, with the subject left out when it is the path."""
    path = finding.path.as_posix() if finding.path is not None else "<path>"
    subject = "" if finding.subject in (None, path) else f" {finding.subject}"
    return f'{TRAILER_KEY}: {finding.code} {path}{subject} reason="{REASON_PLACEHOLDER}"'


def trailer_form(code: str) -> str:
    """The shape of a trailer that acknowledges `code`, for `irminsul explain`."""
    return f'{TRAILER_KEY}: {code} <path> [<subject>] reason="{REASON_PLACEHOLDER}"'


def trailer_open(finding: Finding) -> bool:
    """Whether a trailer can still take `finding`: its code declares `trailer`, and no trailer
    of the change has accepted it yet."""
    from irminsul.checks.pipeline import answer_of

    return answer_of(finding.code).kind is AnswerKind.trailer and not accepted(finding)


def trailer_block(findings: Iterable[Finding]) -> list[str]:
    """The trailers the open findings can take, under one heading, or nothing when none can."""
    open_findings = [finding for finding in findings if trailer_open(finding)]
    if not open_findings:
        return []
    return [
        f"{len(open_findings)} finding(s) can be answered by a trailer, if you have judged them "
        "acceptable; each goes on the commit that carries the last change to its files, or a "
        "later one:",
        *(f"  {trailer_for(finding)}" for finding in open_findings),
    ]


_FIX_THE_TRAILER: Final = f"add a valid trailer to a later commit: `{trailer_form('<code>')}`"


def apply_acknowledgements(
    findings: list[Finding], graph: DocGraph, *, ran: Collection[str] | None
) -> list[Finding]:
    """`findings` with the change's trailers applied. A graph with no change has none, so its
    findings come back unchanged."""
    if graph.change is None or graph.repo_root is None:
        return findings
    trailers = reviewed_trailers(graph.git, graph.repo_root, graph.change)
    return acknowledge(findings, trailers, graph, ran=ran)


def reviewed_trailers(git: GitReader, repo_root: Path, change: ChangeRange) -> list[Trailer]:
    """The `Irminsul-Reviewed` trailers in the range, each with what later changes touched.

    Work not yet committed is later than every commit. When git cannot say what changed
    after a commit, everything in the range counts as later, so a trailer whose reach is
    unknown acknowledges nothing.
    """
    from irminsul.git.changes import GitChangesError, commit_trailers, files_changed_after

    try:
        read = commit_trailers(git, repo_root, change.base, change.commit, TRAILER_KEY)
        changed_after: dict[str, frozenset[str]] = {}
        for commit, _ in read:
            if commit not in changed_after:
                after = files_changed_after(git, repo_root, commit, change.commit, change.base)
                changed_after[commit] = (
                    change.changed if after is None else after | change.uncommitted
                )
    except GitChangesError:
        return []
    return [Trailer(commit, value, changed_after[commit]) for commit, value in read]


def _read(trailer: Trailer, graph: DocGraph) -> _Named | _Problem:
    parsed = parse(trailer.value)
    if isinstance(parsed, str):
        return _Problem(parsed, _FIX_THE_TRAILER)
    code = _code_named(parsed.code)
    if isinstance(code, _Problem):
        return code
    path = _spelled_from_root(graph.repo_root, parsed.path)
    return _Named(trailer, code, path, parsed.subject or path, parsed.reason)


def _code_named(name: str) -> str | _Problem:
    """The finding code a trailer names. A bare check name stands for its one code, which only
    a check with exactly one code allows."""
    from irminsul.checks.pipeline import answer_of, class_of, finding_sources

    if "/" not in name:
        source = finding_sources().get(name)
        if source is None:
            return _Problem(f"names {name}, which is no check or finding code", _FIX_THE_TRAILER)
        if len(source.explanations) != 1:
            return _Problem(
                f"names the check {name}, which has several codes: name the one code",
                _FIX_THE_TRAILER,
            )
        (name,) = source.explanations
    if class_of(name) is None:
        return _Problem(f"names {name}, which is no finding code", _FIX_THE_TRAILER)
    answer = answer_of(name)
    if answer.kind is not AnswerKind.trailer:
        return _Problem(
            f"names {name}, which is answered by {answer.kind.value}, not by a trailer",
            f"`{name}` is answered by {answer.kind.value}; `irminsul explain {name}` says how",
        )
    return name


def _same_target(finding: Finding, named: _Named) -> bool:
    """Whether `finding` is on the path and subject the trailer names, whatever its code."""
    return (
        finding.path is not None
        and finding.path.as_posix() == named.path
        and finding.subject == named.subject
    )


def _matches(finding: Finding, named: _Named) -> bool:
    return finding.code == named.code and _same_target(finding, named)


def _judge(finding: Finding, hits: list[_Named], graph: DocGraph) -> Finding:
    about = about_of(finding)
    live = [hit for hit in hits if not set(about) & hit.trailer.changed_after]
    if live:
        quoted = "; ".join(f'{hit.trailer.commit}: "{hit.reason}"' for hit in live)
        return replace(
            finding,
            severity=Severity.info,
            message=f"{finding.message}; acknowledged in {quoted}",
            suggestion=None,
            data={
                **(finding.data or {}),
                ACKNOWLEDGED_IN: ", ".join(hit.trailer.commit for hit in live),
                REASON: "; ".join(hit.reason for hit in live),
            },
        )
    uncommitted = graph.change.uncommitted if graph.change is not None else frozenset()
    note = "; ".join(
        f"{hit.trailer.commit}, which predates the change to "
        + ", ".join(
            shown_path(path, uncommitted) for path in about if path in hit.trailer.changed_after
        )
        + ": that trailer does not count"
        for hit in hits
    )
    own = finding.suggestion
    return replace(finding, suggestion=note if own is None else f"{own} ({note})")


def _invalid(trailer: Trailer, problem: _Problem) -> Finding:
    return Finding(
        check=CHECK_NAME,
        code=CODE_INVALID,
        severity=Severity.info,
        message=f"the {TRAILER_KEY} trailer in {trailer.commit} {problem.problem}: {trailer.value}",
        suggestion=problem.suggestion,
    )


def _unused(named: _Named, findings: list[Finding]) -> Finding:
    codes = _codes_on(named, findings)
    message = (
        f"the {TRAILER_KEY} trailer in {named.trailer.commit} matches no finding in this "
        f"change, so it does nothing: {named.trailer.value}"
    )
    for code in codes:
        message += (
            f"; the finding on `{named.path}` `{named.subject}` is `{code}`, not `{named.code}`"
        )
    return Finding(
        check=CHECK_NAME,
        code=CODE_UNUSED,
        severity=Severity.info,
        message=message,
        path=Path(named.path),
        suggestion=_unused_suggestion(codes),
    )


def _unused_suggestion(codes: list[str]) -> str:
    """What to do with an unused trailer. A finding on the same target that a trailer can
    still take is open, so "nothing to do" would be false: the trailer named the wrong code."""
    if not codes:
        return _UNUSED_SUGGESTION
    named = ", ".join(f"`{code}`" for code in codes)
    if len(codes) == 1:
        return f"add a trailer naming {named} to a later commit, if the finding is acceptable"
    return f"add a trailer naming each of {named} to a later commit, if the findings are acceptable"


def _codes_on(named: _Named, findings: list[Finding]) -> list[str]:
    """The other codes that findings on the trailer's path and subject carry, where a trailer
    answers the code: the trailer named the wrong one."""
    from irminsul.checks.pipeline import answer_of

    return sorted(
        {
            finding.code
            for finding in findings
            if finding.code != named.code
            and _same_target(finding, named)
            and answer_of(finding.code).kind is AnswerKind.trailer
        }
    )
