"""Check protocol, finding model, and reporting helpers.

Every check ingests a `DocGraph` and returns a list of `Finding`s. The CLI
prints them and uses their severity to decide the exit code.
"""

from __future__ import annotations

from collections.abc import Callable
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

    `certain` findings prove the tree breaks a rule and are errors. `hint` findings
    need judgment and never error. `time` findings come from elapsed time or the
    outside world, never error, and are left out of a run given a diff range.
    """

    certain = "certain"
    hint = "hint"
    time = "time"


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
    category: str | None = None
    #: Machine-readable decomposition of the finding for agents. When set, it
    #: always carries a kebab-case "problem" key; all values are strings.
    data: dict[str, str] | None = None

    def __post_init__(self) -> None:
        # `code` and `category` describe the same kind slug from two eras —
        # `category` predates codes and still keys `fixes()` in some checks.
        # When a site sets both, they must agree; deriving one from the other
        # instead would silently populate `category` (visible in JSON output
        # and fix keying) on every finding, changing behavior.
        if self.category is not None and self.code != f"{self.check}/{self.category}":
            raise ValueError(
                f"finding code {self.code!r} disagrees with its category: "
                f"expected '{self.check}/{self.category}'"
            )


@dataclass(frozen=True)
class Fix:
    path: Path
    description: str
    apply: Callable[[str], str]
    requires_confirm: bool = False


@runtime_checkable
class Check(Protocol):
    """A check's shape.

    A check may also declare `drafts_exempt: ClassVar[frozenset[str]]`, the certain
    codes that report a doc as unfinished rather than as wrong about something outside
    it. Only those are demoted to warnings on a draft doc: a half-written doc may be
    half-written, but it may not point at a symbol that does not exist. It is optional
    rather than part of this protocol so the great majority of checks, which exempt
    nothing, stay silent about it; `pipeline._drafts_exempt` collects what is declared.
    """

    name: ClassVar[str]
    default_severity: ClassVar[Severity]
    #: Every code this check can emit, mapped to a one-to-two-sentence
    #: explanation of what the finding kind means and how to fix it. Keyed by
    #: the full `<check-name>/<kind-slug>` code. Read by `irminsul explain`.
    explanations: ClassVar[dict[str, str]]
    #: The class of every code in `explanations`.
    classes: ClassVar[dict[str, FindingClass]]

    def run(self, graph: DocGraph) -> list[Finding]: ...


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


def fix_commands(findings: list[Finding], graph: DocGraph, *, profile: str) -> list[str | None]:
    """The `irminsul fix` invocation that remediates each finding, or None.

    Mirrors the fix command's harvest: every check implementing
    `fixes(findings, graph)` is asked, per finding, whether that finding alone
    yields at least one `Fix`. The command repeats the profile the finding was
    produced under, because `fix --check` only selects checks that are active
    under its own profile, and appends `--confirm` when a harvested fix would
    otherwise be held back.
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
        profile_flag = "" if profile == "enabled" else f" --profile {profile}"
        command = f"irminsul fix{profile_flag} --check {finding.check}"
        if any(fix.requires_confirm for fix in harvested):
            command += " --confirm"
        out.append(command)
    return out


def finding_records(findings: list[Finding], commands: list[str | None]) -> list[dict[str, object]]:
    """The JSON shape of a finding, shared by every findings-emitting surface.

    `class` is what the code declares and `effective_class` what this occurrence
    enforces as; they differ only where the draft exemption demoted a certain finding.
    Read `effective_class` to predict the exit code — `class` alone cannot, which is
    why both are reported.
    """
    from irminsul.checks.pipeline import class_of, effective_class

    records: list[dict[str, object]] = []
    for finding, command in zip(findings, commands, strict=True):
        finding_class = class_of(finding.code)
        enforced = effective_class(finding)
        record: dict[str, object] = {
            "check": finding.check,
            "code": finding.code,
            "class": finding_class.value if finding_class is not None else None,
            "effective_class": enforced.value if enforced is not None else None,
            "severity": finding.severity.value,
            "message": finding.message,
            "path": finding.path.as_posix() if finding.path else None,
            "doc_id": finding.doc_id,
            "line": finding.line,
            "suggestion": finding.suggestion,
            "category": finding.category,
            "data": finding.data,
            "fixable": command is not None,
        }
        if command is not None:
            record["fix_command"] = command
        records.append(record)
    return records
