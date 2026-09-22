"""Repository binding readiness: the pre-proposal baseline.

Composes existing deterministic checks into one lifecycle-aware summary an
agent runs before drafting a new proposal: errors, which are certain findings, are
blockers, known drift signals — stale anchors, undocumented source, lifecycle debt,
mtime drift — are clues with source paths, and unrelated warnings are reported as
repository debt
without preventing a new idea from being recorded. The report proves
mechanical freshness only; it never claims behavior is true.
"""

from __future__ import annotations

import json
from collections import Counter
from dataclasses import dataclass
from pathlib import Path

from irminsul.checks import Finding, Severity, sort_findings
from irminsul.checks.pipeline import enabled_findings
from irminsul.config import IrminsulConfig
from irminsul.docgraph import DocGraph, build_graph

READINESS_VERSION = 1

# Checks whose warnings are drift *clues* for new work rather than background
# debt: they mark bindings that are no longer fresh.
_CLUE_CHECKS = frozenset(
    {
        "claim-anchor",
        "rfc-follow-through",
        "mtime-drift",
        "change-binding",
        "inventory-drift",
        "uniqueness",
    }
)


@dataclass(frozen=True)
class ReadinessItem:
    check: str
    message: str
    path: str | None
    suggestion: str | None


@dataclass(frozen=True)
class BindingReadinessReport:
    version: int
    ready: bool
    """True when no enabled check reports an error, so the graph can be trusted."""
    blockers: tuple[ReadinessItem, ...]
    clues: tuple[ReadinessItem, ...]
    repository_debt: tuple[tuple[str, int], ...]
    """(check name, warning count) for enabled findings that are neither blockers
    nor drift clues."""


def build_binding_readiness_report(
    repo_root: Path,
    config: IrminsulConfig,
    *,
    graph: DocGraph | None = None,
) -> BindingReadinessReport:
    if graph is None:
        graph = build_graph(repo_root, config)

    findings = enabled_findings(graph)

    blockers = [_item(f) for f in sort_findings(findings) if f.severity == Severity.error]

    clues: list[ReadinessItem] = []
    debt: Counter[str] = Counter()
    for finding in sort_findings(findings):
        if finding.severity != Severity.warning:
            continue
        if finding.check in _CLUE_CHECKS:
            clues.append(_item(finding))
        else:
            debt[finding.check] += 1

    return BindingReadinessReport(
        version=READINESS_VERSION,
        ready=not blockers,
        blockers=tuple(blockers),
        clues=tuple(clues),
        repository_debt=tuple(sorted(debt.items())),
    )


def _item(finding: Finding) -> ReadinessItem:
    return ReadinessItem(
        check=finding.check,
        message=finding.message,
        path=finding.path.as_posix() if finding.path else None,
        suggestion=finding.suggestion,
    )


def binding_readiness_to_json(report: BindingReadinessReport) -> str:
    return json.dumps(
        {
            "version": report.version,
            "ready": report.ready,
            "blockers": [_item_dict(i) for i in report.blockers],
            "clues": [_item_dict(i) for i in report.clues],
            "repository_debt": [
                {"check": check, "findings": count} for check, count in report.repository_debt
            ],
        },
        indent=2,
    )


def _item_dict(item: ReadinessItem) -> dict[str, object]:
    return {
        "check": item.check,
        "message": item.message,
        "path": item.path,
        "suggestion": item.suggestion,
    }


def format_binding_readiness_plain(report: BindingReadinessReport) -> str:
    lines = [f"binding readiness: {'ready' if report.ready else 'blocked'}"]
    if report.blockers:
        lines.append("  blockers (errors):")
        for item in report.blockers:
            location = f"{item.path}: " if item.path else ""
            lines.append(f"    [{item.check}] {location}{item.message}")
    if report.clues:
        lines.append(f"  drift clues: {len(report.clues)}")
        for item in report.clues[:10]:
            location = f"{item.path}: " if item.path else ""
            lines.append(f"    [{item.check}] {location}{item.message}")
        if len(report.clues) > 10:
            lines.append(f"    ... and {len(report.clues) - 10} more")
    if report.repository_debt:
        debt = ", ".join(f"{check} {count}" for check, count in report.repository_debt)
        lines.append(f"  repository debt (unrelated findings): {debt}")
    return "\n".join(lines)
