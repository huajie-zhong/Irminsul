"""Check protocol, finding model, and reporting helpers.

Every check ingests a `DocGraph` and returns a list of `Finding`s. The CLI
prints them and uses their class to decide the exit code.
"""

from __future__ import annotations

from collections.abc import Callable, Collection
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from typing import ClassVar, Protocol, runtime_checkable

from irminsul.docgraph import DocGraph, DocNode


class Severity(StrEnum):
    error = "error"
    warning = "warning"
    info = "info"


class FindingClass(StrEnum):
    """How sure a finding is, which decides whether it blocks.

    `certain` findings prove the tree breaks a rule and are errors, unless they report a
    draft doc as unfinished or a trailer of the change accepts them. `hint` findings need
    judgment and never error. `time` findings come from elapsed time or the outside world,
    never error, and are left out of a run given a diff range.
    """

    certain = "certain"
    hint = "hint"
    time = "time"


class AnswerKind(StrEnum):
    """How a correct doc answers a finding of a code, which lasts as long as what it reports.

    `fix`: the doc or config is wrong whenever the finding fires. `line`: an ignore comment
    on the finding's line waives it as long as the mismatch lasts. `pin`: a re-pin records
    the content as re-read, until it moves again. `trailer`: an `Irminsul-Reviewed` commit
    trailer signs off one change.
    """

    fix = "fix"
    line = "line"
    pin = "pin"
    trailer = "trailer"


@dataclass(frozen=True)
class Answer:
    """The answer a code declares: its kind, and `how`, the sentence a reader acts on."""

    kind: AnswerKind
    how: str

    @classmethod
    def fix(cls, how: str) -> Answer:
        return cls(AnswerKind.fix, how)

    @classmethod
    def line(cls, how: str) -> Answer:
        return cls(AnswerKind.line, how)

    @classmethod
    def pin(cls, how: str) -> Answer:
        return cls(AnswerKind.pin, how)

    @classmethod
    def trailer(cls, how: str) -> Answer:
        return cls(AnswerKind.trailer, how)


_SEVERITY_ORDER = {Severity.error: 0, Severity.warning: 1, Severity.info: 2}


@dataclass(frozen=True)
class Finding:
    check: str
    severity: Severity
    message: str
    #: Stable identity of the message template this finding was built from,
    #: shaped `<check-name>/<kind-slug>` (e.g. `links/broken-link`). One code
    #: per distinct message template a check emits, not per occurrence — it
    #: survives wording changes across releases, unlike the free-text
    #: `message`. Looked up by `irminsul explain <code>`.
    code: str
    path: Path | None = None
    doc_id: str | None = None
    line: int | None = None
    suggestion: str | None = None
    #: Machine-readable decomposition of the finding for agents, beyond what `code`
    #: names; all values are strings.
    data: dict[str, str] | None = None
    #: The item a sign-off names: a claim id, a setting's dotted name, or the path itself
    #: for a finding about a whole file. A finding of a code declared `trailer` carries one.
    subject: str | None = None
    #: The files whose later change lapses a trailer that acknowledges this finding. Empty
    #: means the finding's own path.
    about: tuple[str, ...] = ()


@dataclass(frozen=True)
class Fix:
    path: Path
    description: str
    apply: Callable[[str], str]
    requires_confirm: bool = False
    #: The fix writes a file that does not exist yet; `apply` then receives "". Any other
    #: fix whose file is missing is an error, never a new file.
    creates: bool = False


class CheckFlag(StrEnum):
    """A fact a check declares about itself, which other parts of the tool act on.

    A check lists its flags in `flags`, and the set of checks carrying one is derived from
    the registry by `irminsul.checks.flagged`, so a flag cannot be missing from a list kept
    elsewhere and a renamed check keeps its flags.
    """

    #: Registered, but off unless a project lists it in `checks.enabled`.
    opt_in = "opt-in"
    #: Answers from commit history, so a truncated history silently turns it into a no-op.
    reads_history = "reads-history"
    #: Takes its exceptions from the adoption record, which the `adoption-record` pass validates.
    consults_adoption_record = "consults-adoption-record"
    #: Reaches the network, which `orient` stays off.
    uses_network = "uses-network"


class FindingSource(Protocol):
    """A named producer of findings, which is all `irminsul explain` and the finding-code
    registry need to describe its codes.

    A source may also declare `drafts_exempt: ClassVar[frozenset[str]]`, the certain
    codes that report a doc as unfinished rather than as wrong about something outside
    it. Only those are demoted to warnings on a draft doc: a half-written doc may be
    half-written, but it may not point at a symbol that does not exist. It may declare
    `audits_suppression` the same way, the codes that report on a suppression marker,
    `flags: ClassVar[frozenset[CheckFlag]]`, and `answers: ClassVar[dict[str, Answer]]`, the
    answer of every hint and time code it explains and of each certain code a trailer
    answers; a code it leaves out is answered by the fix its explanation gives. Each is
    optional rather than part of this protocol so the sources that declare none stay silent
    about it; `pipeline` collects what is declared, and a test holds every hint and time
    code to an answer.
    """

    name: ClassVar[str]
    default_severity: ClassVar[Severity]
    #: Every code this source can emit, mapped to a one-to-two-sentence
    #: explanation of what the finding kind means and how to fix it. Keyed by
    #: the full `<check-name>/<kind-slug>` code. Read by `irminsul explain`.
    explanations: ClassVar[dict[str, str]]
    #: The class of every code in `explanations`.
    classes: ClassVar[dict[str, FindingClass]]


def flags_of(source: type[FindingSource]) -> frozenset[CheckFlag]:
    return getattr(source, "flags", frozenset())


@runtime_checkable
class Check(FindingSource, Protocol):
    """A check: a judgment about the graph, registered in `REGISTRY` and run when
    `checks.enabled` names it."""

    def run(self, graph: DocGraph) -> list[Finding]: ...


class Pass(FindingSource, Protocol):
    """A judgment about the run rather than the graph, in `PASSES` instead of `REGISTRY`.

    `checks.enabled` is a list a repository writes, so a rule that must hold whatever it
    says cannot be a check. Every run calls every pass, with `selected`, the names of the
    checks that run is making. A pass that judges a change reads its range from
    `graph.change`, and reports nothing when the graph carries none.
    """

    def run(self, graph: DocGraph, selected: Collection[str]) -> list[Finding]: ...


def certain_severity(node: DocNode) -> Severity:
    """The severity of a certain finding about `node`: an error, or a warning while the
    doc is a draft and so still work in progress."""
    from irminsul.frontmatter import StatusEnum

    return Severity.warning if node.frontmatter.status == StatusEnum.draft else Severity.error


def carries_certain_findings(node: DocNode) -> bool:
    """Whether a check reports its certain findings about `node`.

    A draft is read like a stable doc. What a draft is excused is decided per code, by
    `drafts_exempt`; a check that skipped drafts outright would excuse every code it has,
    and one word of frontmatter would clear them. A deprecated or removed doc describes
    what is gone, so it is not read.
    """
    from irminsul.frontmatter import StatusEnum

    return node.frontmatter.status in (StatusEnum.stable, StatusEnum.draft)


def certain_audit_nodes(graph: DocGraph) -> list[DocNode]:
    return [node for node in graph.nodes.values() if carries_certain_findings(node)]


def sort_findings(findings: list[Finding]) -> list[Finding]:
    """Errors first, then warnings, then info; stable on (path, line, check)."""
    return sorted(
        findings,
        key=lambda f: (
            _SEVERITY_ORDER[f.severity],
            str(f.path) if f.path else "",
            f.line if f.line is not None else -1,
            f.check,
        ),
    )


def summarize(findings: list[Finding]) -> dict[Severity, int]:
    counts = {s: 0 for s in Severity}
    for f in findings:
        counts[f.severity] += 1
    return counts


def fix_commands(findings: list[Finding], graph: DocGraph) -> list[str | None]:
    """The `irminsul fix` invocation that remediates each finding, or None.

    Mirrors the fix command's harvest: every check implementing
    `fixes(findings, graph)` is asked, per finding, whether that finding alone
    yields at least one `Fix`. The command names the check with `--only`, which
    selects it whether or not it is enabled, and appends `--confirm` when a
    harvested fix would otherwise be held back.
    """
    from irminsul.checks import REGISTRY

    instances: dict[str, Check | None] = {}
    out: list[str | None] = []
    for finding in findings:
        if finding.check not in instances:
            cls = REGISTRY.get(finding.check)
            instances[finding.check] = cls() if cls is not None else None
        instance = instances[finding.check]
        maybe_fixes = getattr(instance, "fixes", None)
        harvested: list[Fix] = maybe_fixes([finding], graph) if maybe_fixes is not None else []
        if not harvested:
            out.append(None)
            continue
        command = f"irminsul fix --only {finding.check}"
        if any(fix.requires_confirm for fix in harvested):
            command += " --confirm"
        out.append(command)
    return out


def finding_records(findings: list[Finding], graph: DocGraph | None) -> list[dict[str, object]]:
    """The JSON shape of a finding, shared by every findings-emitting surface.

    `class` is what the code declares and `effective_class` what this occurrence
    enforces as; they differ where the draft exemption demoted a certain finding, or a
    trailer of the change accepted one.
    Read `effective_class` to predict the exit code — `class` alone cannot, which is
    why both are reported.

    `answer` is the kind of answer the code declares, and `subject` the item a sign-off
    names. `trailer` is the commit trailer that would accept the finding, when one still can. `fixable` and `fix_command` come from `fix_commands` over `graph`. A surface with
    no graph to ask claims nothing is fixable.
    """
    from irminsul.checks.acknowledgement import trailer_for, trailer_open
    from irminsul.checks.pipeline import answer_of, class_of, effective_class

    commands = fix_commands(findings, graph) if graph is not None else [None] * len(findings)
    records: list[dict[str, object]] = []
    for finding, command in zip(findings, commands, strict=True):
        finding_class = class_of(finding.code)
        enforced = effective_class(finding)
        record: dict[str, object] = {
            "check": finding.check,
            "code": finding.code,
            "class": finding_class.value if finding_class is not None else None,
            "effective_class": enforced.value if enforced is not None else None,
            "answer": answer_of(finding.code).kind.value,
            "trailer": trailer_for(finding) if trailer_open(finding) else None,
            "subject": finding.subject,
            "severity": finding.severity.value,
            "message": finding.message,
            "path": finding.path.as_posix() if finding.path else None,
            "doc_id": finding.doc_id,
            "line": finding.line,
            "suggestion": finding.suggestion,
            "data": finding.data,
            "fixable": command is not None,
        }
        if command is not None:
            record["fix_command"] = command
        records.append(record)
    return records
