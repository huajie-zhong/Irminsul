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

# The root-level harness router, which every agent harness reads natively and
# `irminsul init` scaffolds. Reported ahead of the docs-root entries because it
# is the first read, not because it lives in the docs tree — it does not.
# Deliberately narrower than `_ENTRY_DOC_NAMES`: a root README or CONTRIBUTING
# duplicates its docs-root counterpart as noise, and harness-proprietary names
# do not belong in a harness-neutral report.
_ROOT_ENTRY_DOC_NAMES = ("AGENTS.md",)

# Curated command vocabulary teaching an agent the workflow loop. Static by
# design: the *surface* is derivable (`irminsul surface cli`), but the "when"
# guidance is intent, which only a human can curate.
_COMMANDS: tuple[tuple[str, str], ...] = (
    (
        "irminsul context --before-edit <path...>",
        "start an edit: package owners, tests, active RFCs, requirements, and findings",
    ),
    (
        "irminsul context --after-edit",
        "finish an edit: inspect changed paths, affected knowledge, and hard validation",
    ),
    (
        "irminsul context <path>",
        "before editing a known file: find its owning doc, tests, dependencies, and findings",
    ),
    (
        "irminsul context --topic <query>",
        "before locating files: find the docs that cover a topic",
    ),
    (
        "irminsul context --changed",
        "after editing: inspect ownership, tests, dependencies, and findings for this worktree",
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
        "irminsul status --format json",
        "audit repository-wide documentation health, source ownership, and finding totals",
    ),
    (
        "irminsul fix",
        "auto-apply deterministic remediations for fixable findings",
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
        "irminsul change graph [<rfc-id>] --format json",
        "inspect RFC dependencies, replacements, cycles, and lifecycle contradictions",
    ),
    (
        "irminsul new rfc <title>",
        "start a change: reports repository binding readiness, then scaffolds the RFC",
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
        checks=ChecksSummary(
            hard=list(config.checks.hard),
            soft_deterministic=list(config.checks.soft_deterministic),
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
        },
        "commands": [{"command": hint.command, "when": hint.when} for hint in report.commands],
    }
