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

from irminsul.docgraph import DocGraph


class Severity(StrEnum):
    error = "error"
    warning = "warning"
    info = "info"


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


@dataclass(frozen=True)
class Fix:
    path: Path
    description: str
    apply: Callable[[str], str]
    requires_confirm: bool = False


@runtime_checkable
class Check(Protocol):
    name: ClassVar[str]
    default_severity: ClassVar[Severity]
    #: Every code this check can emit, mapped to a one-to-two-sentence
    #: explanation of what the finding kind means and how to fix it. Keyed by
    #: the full `<check-name>/<kind-slug>` code. Read by `irminsul explain`.
    explanations: ClassVar[dict[str, str]]

    def run(self, graph: DocGraph) -> list[Finding]: ...


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
    from irminsul.checks import HARD_REGISTRY, SOFT_REGISTRY

    instances: dict[str, Check | None] = {}
    out: list[str | None] = []
    for finding in findings:
        if finding.check not in instances:
            cls = HARD_REGISTRY.get(finding.check) or SOFT_REGISTRY.get(finding.check)
            instances[finding.check] = cls() if cls is not None else None
        instance = instances[finding.check]
        maybe_fixes = getattr(instance, "fixes", None)
        harvested: list[Fix] = maybe_fixes([finding], graph) if maybe_fixes is not None else []
        if not harvested:
            out.append(None)
            continue
        command = f"irminsul fix --profile {profile} --check {finding.check}"
        if any(fix.requires_confirm for fix in harvested):
            command += " --confirm"
        out.append(command)
    return out


def finding_records(findings: list[Finding], commands: list[str | None]) -> list[dict[str, object]]:
    """The JSON shape of a finding, shared by every findings-emitting surface."""
    records: list[dict[str, object]] = []
    for finding, command in zip(findings, commands, strict=True):
        record: dict[str, object] = {
            "check": finding.check,
            "code": finding.code,
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
