"""First-call orientation report for agents.

`irminsul orient` is the recommended first command in any Irminsul-managed
repo: one `build_graph()` pass plus config, no check execution. It tells an
agent what the docs tree looks like (layers, totals, entry docs), which checks
are configured, and which commands to use next — the workflow vocabulary.
"""

from __future__ import annotations

import json
from collections import Counter
from dataclasses import dataclass
from pathlib import Path, PurePosixPath

from irminsul.config import IrminsulConfig
from irminsul.docgraph import build_graph

# Repo-conventional navigation files an agent should read first, in priority
# order. Only the ones that actually exist on disk are reported.
_ENTRY_DOC_NAMES = ("AGENTS.md", "README.md", "CONTRIBUTING.md", "GLOSSARY.md")

# Curated command vocabulary teaching an agent the workflow loop. Static by
# design: the *surface* is derivable (`irminsul surface cli`), but the "when"
# guidance is intent, which only a human can curate.
_COMMANDS: tuple[tuple[str, str], ...] = (
    (
        "irminsul context --changed",
        "before and after editing: see which docs own your edits, their tests, and findings",
    ),
    (
        "irminsul context --topic <query>",
        "find the docs that cover a topic before starting work",
    ),
    (
        "irminsul context <path>",
        "look up the owning doc, tests, and dependencies for one file",
    ),
    (
        "irminsul refs <doc-or-symbol>",
        "enumerate inbound references before renaming or moving anything",
    ),
    (
        "irminsul surface <kind> --format json",
        "derive the current code surface (cli, http, exports, env-vars) instead of trusting prose",
    ),
    (
        "irminsul check --profile=hard --format json",
        "verify the docs tree before committing; error findings block CI",
    ),
    (
        "irminsul fix",
        "auto-apply deterministic remediations for fixable findings",
    ),
    (
        "irminsul list undocumented",
        "find source files in covered directories that no doc claims",
    ),
)

# The command vocabulary's accuracy and completeness is governed by the
# watched-surface check (RFC 0027) via orient.md's `inventory:` block — every
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
    hard: list[str]
    soft_deterministic: list[str]
    soft_llm: list[str]


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


def build_orient_report(repo_root: Path, config: IrminsulConfig) -> OrientReport:
    """Build the orientation report from one graph walk plus config.

    Fast by construction: no checks run here.
    """
    graph = build_graph(repo_root, config)
    docs_root = config.paths.docs_root.strip("/\\")

    layer_counts: Counter[str] = Counter()
    status_counts: Counter[str] = Counter()
    for node in graph.nodes.values():
        status_counts[node.frontmatter.status.value] += 1
        try:
            rel = node.path.relative_to(docs_root)
        except ValueError:
            continue
        if len(rel.parts) >= 2:
            layer_counts[rel.parts[0]] += 1

    entry_docs = [
        (PurePosixPath(docs_root) / name).as_posix()
        for name in _ENTRY_DOC_NAMES
        if (repo_root / docs_root / name).is_file()
    ]

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
        checks=ChecksSummary(
            hard=list(config.checks.hard),
            soft_deterministic=list(config.checks.soft_deterministic),
            soft_llm=list(config.checks.soft_llm),
        ),
        commands=[CommandHint(command=cmd, when=when) for cmd, when in _COMMANDS],
    )


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

    lines.append("checks:")
    lines.append(f"  hard: {_format_list(report.checks.hard)}")
    lines.append(f"  soft deterministic: {_format_list(report.checks.soft_deterministic)}")
    lines.append(f"  soft llm: {_format_list(report.checks.soft_llm)}")

    lines.append("commands:")
    for hint in report.commands:
        lines.append(f"  {hint.command}")
        lines.append(f"      {hint.when}")

    return "\n".join(lines)


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
        "checks": {
            "hard": report.checks.hard,
            "soft_deterministic": report.checks.soft_deterministic,
            "soft_llm": report.checks.soft_llm,
        },
        "commands": [{"command": hint.command, "when": hint.when} for hint in report.commands],
    }
