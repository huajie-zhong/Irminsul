"""Check protocol, finding model, and reporting helpers.

Every check ingests a `DocGraph` and returns a list of `Finding`s. The CLI
prints them and uses their severity to decide the exit code.
"""

from __future__ import annotations

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
    path: Path | None = None
    doc_id: str | None = None
    line: int | None = None


@runtime_checkable
class Check(Protocol):
    name: ClassVar[str]
    default_severity: ClassVar[Severity]

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
