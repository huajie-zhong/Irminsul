"""`irminsul status` — one-glance digest of the doc system's health.

`check` answers "is anything broken?"; `status` answers "what state is my doc
system in?". The headline is source-file coverage: on a brownfield repo the
uniqueness omission warning only fires inside directories that already contain
a claimed file, so a tree of source files no doc claims keeps `check` green
and `list undocumented` empty. `status` counts that debt directly and names
the directories with the most unclaimed files so an adopter knows where to
start.

Two layers, same shape as `context`: a pure `build_status_report` plus
renderers (`status_report_to_json`, `format_status_plain`). The CLI wiring in
`cli.py` is a thin dispatch.
"""

from __future__ import annotations

import json
from collections import Counter
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path, PurePosixPath

from irminsul.checks import REGISTRY, Finding, Severity, finding_records, sort_findings
from irminsul.checks.globs import walk_configured_source_files
from irminsul.checks.pipeline import is_time, run_check
from irminsul.checks.uniqueness import resolve_claims
from irminsul.config import IrminsulConfig, doc_folder
from irminsul.docgraph import DocGraph, build_graph

_TOP_DIR_LIMIT = 5
_ROOT_LAYER = "(root)"


@dataclass(frozen=True)
class UndocumentedDir:
    """A directory ranked by how many of its files no doc claims."""

    path: str
    undocumented: int


@dataclass(frozen=True)
class StatusReport:
    version: int
    project_name: str
    docs_root: str
    docs_total: int
    docs_by_layer: dict[str, int]
    docs_by_status: dict[str, int]
    source_files: int
    claimed: int
    undocumented: int
    coverage_percent: float | None
    top_undocumented_dirs: list[UndocumentedDir]
    errors: int
    warnings: int
    info: int
    findings_by_check: dict[str, int]
    time_findings: list[Finding] = field(default_factory=list)


def build_status_report(repo_root: Path, config: IrminsulConfig) -> StatusReport:
    """Build the digest: docs inventory, source coverage, findings summary."""
    graph = build_graph(repo_root, config)

    docs_by_layer: Counter[str] = Counter()
    docs_by_status: Counter[str] = Counter()
    for node in graph.nodes.values():
        docs_by_layer[doc_folder(config, node.path) or _ROOT_LAYER] += 1
        docs_by_status[node.frontmatter.status.value] += 1

    source_files = walk_configured_source_files(repo_root, config).files
    claims = resolve_claims(graph, source_files)
    displays = [display for _, display in source_files]
    unclaimed = [display for display in displays if display not in claims]

    total = len(displays)
    claimed = total - len(unclaimed)
    percent = round(100.0 * claimed / total, 1) if total else None

    dir_counts: Counter[str] = Counter(
        PurePosixPath(display).parent.as_posix() for display in unclaimed
    )
    top_dirs = [
        UndocumentedDir(path=path, undocumented=count)
        for path, count in sorted(dir_counts.items(), key=lambda item: (-item[1], item[0]))[
            :_TOP_DIR_LIMIT
        ]
    ]

    findings = _run_configured_checks(config, graph)
    severity_counts = Counter(finding.severity for finding in findings)
    check_counts = Counter(finding.check for finding in findings)

    return StatusReport(
        version=1,
        project_name=config.project_name,
        docs_root=config.paths.docs_root,
        docs_total=len(graph.nodes),
        docs_by_layer=dict(sorted(docs_by_layer.items())),
        docs_by_status=dict(sorted(docs_by_status.items())),
        source_files=total,
        claimed=claimed,
        undocumented=len(unclaimed),
        coverage_percent=percent,
        top_undocumented_dirs=top_dirs,
        errors=severity_counts[Severity.error],
        warnings=severity_counts[Severity.warning],
        info=severity_counts[Severity.info],
        findings_by_check=dict(sorted(check_counts.items())),
        time_findings=sort_findings([finding for finding in findings if is_time(finding)]),
    )


def status_report_to_json(report: StatusReport) -> str:
    data = {
        "version": report.version,
        "project_name": report.project_name,
        "docs_root": report.docs_root,
        "docs": {
            "total": report.docs_total,
            "by_layer": report.docs_by_layer,
            "by_status": report.docs_by_status,
        },
        "coverage": {
            "source_files": report.source_files,
            "claimed": report.claimed,
            "undocumented": report.undocumented,
            "percent": report.coverage_percent,
            "top_undocumented_dirs": [
                {"path": item.path, "undocumented": item.undocumented}
                for item in report.top_undocumented_dirs
            ],
        },
        "findings": {
            "errors": report.errors,
            "warnings": report.warnings,
            "info": report.info,
            "by_check": report.findings_by_check,
            "time": finding_records(report.time_findings, [None] * len(report.time_findings)),
        },
    }
    return json.dumps(data, indent=2)


def format_status_plain(report: StatusReport) -> str:
    lines = [
        f"project: {report.project_name} ({report.docs_root}/)",
        f"docs: {report.docs_total} total",
    ]
    if report.docs_by_layer:
        lines.append("  by layer:")
        lines.extend(f"    {layer}: {count}" for layer, count in report.docs_by_layer.items())
    lines.append(f"  by status: {_format_counts(report.docs_by_status)}")

    if report.source_files:
        lines.append(
            f"coverage: {report.claimed}/{report.source_files} source files claimed "
            f"({report.coverage_percent}%)"
        )
    else:
        lines.append("coverage: no source files found")
    if report.top_undocumented_dirs:
        lines.append("  top undocumented directories:")
        lines.extend(
            f"    {item.undocumented:4d}  {item.path}" for item in report.top_undocumented_dirs
        )

    lines.append(
        "findings: "
        f"{report.errors} error{'s' if report.errors != 1 else ''}, "
        f"{report.warnings} warning{'s' if report.warnings != 1 else ''}, "
        f"{report.info} info"
    )
    if report.findings_by_check:
        lines.append("  by check:")
        lines.extend(f"    {check}: {count}" for check, count in report.findings_by_check.items())
    lines.extend(format_time_findings(report.time_findings))
    lines.append("hint: irminsul check")
    return "\n".join(lines)


def format_time_findings(findings: list[Finding]) -> list[str]:
    """Plain lines for findings that elapsed time produced, which no pull request shows."""
    if not findings:
        return ["time findings: (none)"]
    lines = [f"time findings: {len(findings)}"]
    for finding in findings:
        where = finding.path.as_posix() if finding.path else "-"
        lines.append(f"  {where}  [{finding.code}]  {finding.message}")
    return lines


def _format_counts(counts: Mapping[str, int]) -> str:
    if not counts:
        return "-"
    return ", ".join(f"{key} {value}" for key, value in counts.items())


def _run_configured_checks(config: IrminsulConfig, graph: DocGraph) -> list[Finding]:
    """Run the enabled checks, plus the passes no run may omit.

    `status` answers "is anything wrong here", which is a verdict, so it owes the same
    contract as every other verdict: **a check may delegate error reporting only where the
    calling execution path guarantees that the responsible validation runs.** The ownership
    checks swallow an unreadable adoption record because the `adoption-record` pass reports
    it, and this runner did not run that pass — so `status` said zero errors about a record
    `check` fails on. Unknown names are skipped silently, matching `context`.
    """
    from irminsul.checks.pipeline import finish, mandatory_findings

    names = [name for name in config.checks.enabled if name in REGISTRY]
    findings: list[Finding] = []
    for name in names:
        cls = REGISTRY.get(name)
        if cls is not None:
            findings.extend(run_check(cls, graph))
    findings.extend(finish(mandatory_findings(graph, names), graph))
    return findings
