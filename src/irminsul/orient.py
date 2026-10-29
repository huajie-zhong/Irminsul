"""First-call orientation report for agents.

`irminsul orient` is the recommended first command in any Irminsul-managed
repo: one `build_graph()` pass plus config. It tells an agent what the docs tree
looks like (layers, totals, entry docs), how much of the source a doc owns, which
checks are configured, what elapsed time has made stale, and which commands to use
next — the workflow vocabulary.
"""

from __future__ import annotations

import json
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path, PurePosixPath

from irminsul.checks.base import Finding, finding_records
from irminsul.config import IrminsulConfig, doc_folder
from irminsul.docgraph import DocGraph, build_graph

#: How many of the directories with the most unowned files the coverage block names.
_TOP_DIR_LIMIT = 5

# Repo-conventional navigation files an agent should read first, in priority
# order. Only the ones that actually exist on disk are reported.
_ENTRY_DOC_NAMES = ("AGENTS.md", "README.md", "CONTRIBUTING.md", "GLOSSARY.md")

# The root-level harness router that `irminsul init` scaffolds. Cursor and Codex
# read it natively; Claude Code reaches it through the scaffolded `CLAUDE.md`
# import. Reported ahead of the docs-root entries because it is the first
# read, not because it lives in the docs tree — it does not.
# Deliberately narrower than `_ENTRY_DOC_NAMES`: a root README or CONTRIBUTING
# duplicates its docs-root counterpart as noise, and harness-proprietary names
# do not belong in a harness-neutral report.
_ROOT_ENTRY_DOC_NAMES = ("AGENTS.md",)

# Curated command vocabulary teaching an agent the workflow loop. Static by
# design: the *surface* is derivable (`irminsul surface cli`), but the "when"
# guidance is intent, which only a human can curate.
_COMMANDS: tuple[tuple[str, str], ...] = (
    (
        "irminsul context <path...>",
        "before editing: package owners, tests, active RFCs, requirements, and claims; runs no checks",
    ),
    (
        "irminsul context --after-edit",
        "finish an edit: map changed paths to owners, run the checks, and say what the change introduced",
    ),
    (
        "irminsul context --topic <query>",
        "before locating files: find the docs that cover a topic",
    ),
    (
        "irminsul refs <doc>",
        "enumerate a doc's inbound references before renaming or moving it",
    ),
    (
        "irminsul surface <kind> --format json",
        "derive the current code surface (commands, options, endpoints, exports, env vars) instead of trusting prose",
    ),
    (
        "irminsul check --format json",
        "verify the docs tree before committing; error findings block CI",
    ),
    (
        "irminsul fix",
        "auto-apply deterministic remediations for fixable findings",
    ),
    (
        "irminsul list review --doc <path> --format json",
        "before trusting a doc's claims about behaviour: its sentences that name code, paired with that code",
    ),
    (
        "irminsul list undocumented",
        "find source files in covered directories that no doc claims",
    ),
    (
        "irminsul list lifecycle --queue",
        "discover unfinished decision work and accepted RFCs awaiting implementation",
    ),
    (
        "irminsul change status <rfc-id>",
        "orient on one RFC: lifecycle state, evidence, blockers, and the next action",
    ),
    (
        "irminsul new rfc <title>",
        "start a change: scaffold the RFC; run `irminsul check` first for what the tree fails on",
    ),
)

# The command vocabulary's accuracy and completeness is governed by the
# watched-surface check via orient.md's `inventory:` block — every
# CLI identity must be either taught here or listed under the block's `omit:`.


@dataclass(frozen=True)
class LayerSummary:
    dir: str
    doc_count: int


@dataclass(frozen=True)
class DocTotals:
    total: int
    by_status: dict[str, int]


@dataclass(frozen=True)
class ChecksSummary:
    enabled: list[str]


@dataclass(frozen=True)
class UndocumentedDir:
    """A directory ranked by how many of its files no doc claims."""

    path: str
    undocumented: int


@dataclass(frozen=True)
class SourceCoverage:
    """How much of the managed source a doc owns.

    The checks cannot say this: an unowned file outside every documented directory raises
    no finding, so a repository of undocumented code keeps `check` green.
    """

    source_files: int
    claimed: int
    percent: float | None
    top_undocumented_dirs: list[UndocumentedDir]


@dataclass(frozen=True)
class CommandHint:
    command: str
    when: str


@dataclass(frozen=True)
class OrientReport:
    version: int
    project_name: str
    docs_root: str
    layers: list[LayerSummary]
    doc_totals: DocTotals
    entry_docs: list[str]
    checks: ChecksSummary
    commands: list[CommandHint]
    coverage: SourceCoverage
    time_findings: list[Finding] = field(default_factory=list)


def _entry_docs(repo_root: Path, docs_root: str) -> list[str]:
    """Navigation files an agent should read first, as repo-relative POSIX paths.

    Root-level entries come first — the harness router is read before the
    navigation manifest — then the docs-root entries in their own priority
    order. Only files that exist are reported. The dedup below matters only
    when `docs_root` is the repo root itself, where `AGENTS.md` is reachable
    at both levels and would otherwise be listed twice; under a nested
    `docs_root` the root router and the manifest are distinct files and both
    are reported.
    """
    out: list[str] = []
    for name in _ROOT_ENTRY_DOC_NAMES:
        if (repo_root / name).is_file():
            out.append(PurePosixPath(name).as_posix())
    for name in _ENTRY_DOC_NAMES:
        if not (repo_root / docs_root / name).is_file():
            continue
        rel = (PurePosixPath(docs_root) / name).as_posix()
        if rel not in out:
            out.append(rel)
    return out


def build_orient_report(repo_root: Path, config: IrminsulConfig) -> OrientReport:
    """Build the orientation report from one graph walk plus config.

    The only checks run are the enabled ones that report time findings without the
    network, because what elapsed time made stale shows up on no pull request.
    """
    graph = build_graph(repo_root, config)
    docs_root = config.paths.docs_root.strip("/\\")

    layer_counts: Counter[str] = Counter()
    status_counts: Counter[str] = Counter()
    for node in graph.nodes.values():
        status_counts[node.frontmatter.status.value] += 1
        folder = doc_folder(config, node.path)
        if folder is not None:
            layer_counts[folder] += 1

    entry_docs = _entry_docs(repo_root, docs_root)

    return OrientReport(
        version=1,
        project_name=config.project_name,
        docs_root=docs_root,
        layers=[LayerSummary(dir=d, doc_count=n) for d, n in sorted(layer_counts.items())],
        doc_totals=DocTotals(
            total=len(graph.nodes),
            by_status={status: status_counts[status] for status in sorted(status_counts)},
        ),
        entry_docs=entry_docs,
        checks=ChecksSummary(enabled=list(config.checks.enabled)),
        commands=[CommandHint(command=cmd, when=when) for cmd, when in _COMMANDS],
        coverage=_source_coverage(graph),
        time_findings=_time_findings(config, graph),
    )


def _source_coverage(graph: DocGraph) -> SourceCoverage:
    """Counted by `source_ownership`, the helper `irminsul list undocumented --all` lists
    from, so noise and test files are left out of both and the two cannot disagree."""
    from irminsul.checks.uniqueness import source_ownership

    managed, unclaimed = source_ownership(graph)
    claimed = len(managed) - len(unclaimed)
    dir_counts: Counter[str] = Counter(
        PurePosixPath(display).parent.as_posix() for display in unclaimed
    )
    ranked = sorted(dir_counts.items(), key=lambda item: (-item[1], item[0]))[:_TOP_DIR_LIMIT]
    return SourceCoverage(
        source_files=len(managed),
        claimed=claimed,
        percent=round(100.0 * claimed / len(managed), 1) if managed else None,
        top_undocumented_dirs=[UndocumentedDir(path=p, undocumented=n) for p, n in ranked],
    )


def _time_findings(config: IrminsulConfig, graph: DocGraph) -> list[Finding]:
    from irminsul.checks import REGISTRY, sort_findings
    from irminsul.checks.base import CheckFlag, FindingClass, flags_of
    from irminsul.checks.pipeline import is_time, run_check

    findings: list[Finding] = []
    for name in config.checks.enabled:
        cls = REGISTRY.get(name)
        # orient stays offline
        if cls is None or CheckFlag.uses_network in flags_of(cls):
            continue
        if FindingClass.time in cls.classes.values():
            findings.extend(finding for finding in run_check(cls, graph) if is_time(finding))
    return sort_findings(findings)


def orient_report_to_json(report: OrientReport) -> str:
    return json.dumps(_report_to_dict(report), indent=2)


def format_orient_plain(report: OrientReport) -> str:
    lines = [
        f"project: {report.project_name}",
        f"docs root: {report.docs_root}",
        f"docs: {_format_totals(report.doc_totals)}",
    ]

    lines.append("layers:")
    if report.layers:
        width = max(len(layer.dir) for layer in report.layers)
        lines.extend(f"  {layer.dir.ljust(width)}  {layer.doc_count}" for layer in report.layers)
    else:
        lines.append("  (none)")

    lines.append(f"entry docs: {_format_list(report.entry_docs)}")

    lines.extend(_format_coverage(report.coverage))

    lines.append(f"checks: {_format_list(report.checks.enabled)}")

    lines.extend(_format_time_findings(report.time_findings))

    lines.append("commands:")
    for hint in report.commands:
        lines.append(f"  {hint.command}")
        lines.append(f"      {hint.when}")

    return "\n".join(lines)


def _format_coverage(coverage: SourceCoverage) -> list[str]:
    if not coverage.source_files:
        return ["source coverage: no source files found"]
    lines = [
        f"source coverage: {coverage.claimed}/{coverage.source_files} files owned by a doc "
        f"({coverage.percent}%)"
    ]
    if coverage.top_undocumented_dirs:
        lines.append("  most unowned files (irminsul list undocumented --all lists them):")
        lines.extend(
            f"    {item.undocumented:4d}  {item.path}" for item in coverage.top_undocumented_dirs
        )
    return lines


def _format_time_findings(findings: list[Finding]) -> list[str]:
    """Plain lines for findings that elapsed time produced, which no pull request shows."""
    if not findings:
        return ["time findings: (none)"]
    lines = [f"time findings: {len(findings)}"]
    for finding in findings:
        where = finding.path.as_posix() if finding.path else "-"
        lines.append(f"  {where}  [{finding.code}]  {finding.message}")
    return lines


def _format_totals(totals: DocTotals) -> str:
    if not totals.by_status:
        return "0 total"
    breakdown = ", ".join(f"{status} {count}" for status, count in totals.by_status.items())
    return f"{totals.total} total ({breakdown})"


def _format_list(values: list[str]) -> str:
    return ", ".join(values) if values else "(none)"


def _report_to_dict(report: OrientReport) -> dict[str, object]:
    return {
        "version": report.version,
        "project_name": report.project_name,
        "docs_root": report.docs_root,
        "layers": [{"dir": layer.dir, "doc_count": layer.doc_count} for layer in report.layers],
        "doc_totals": {
            "total": report.doc_totals.total,
            "by_status": report.doc_totals.by_status,
        },
        "entry_docs": report.entry_docs,
        "checks": {"enabled": report.checks.enabled},
        "commands": [{"command": hint.command, "when": hint.when} for hint in report.commands],
        "coverage": {
            "source_files": report.coverage.source_files,
            "claimed": report.coverage.claimed,
            "undocumented": report.coverage.source_files - report.coverage.claimed,
            "percent": report.coverage.percent,
            "top_undocumented_dirs": [
                {"path": item.path, "undocumented": item.undocumented}
                for item in report.coverage.top_undocumented_dirs
            ],
        },
        "findings": {"time": finding_records(report.time_findings, None)},
    }
