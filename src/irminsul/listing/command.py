"""`irminsul list` — enumerate docs by condition."""

from __future__ import annotations

import json
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path, PurePosixPath

import typer

from irminsul.checks.base import Finding, Severity
from irminsul.checks.globs import walk_source_files
from irminsul.checks.orphans import OrphansCheck
from irminsul.checks.stale_reaper import StaleReaperCheck
from irminsul.checks.uniqueness import OMISSION_SKIP, UniquenessCheck, resolve_claims
from irminsul.config import find_config, load
from irminsul.docgraph import build_graph


def list_orphans(repo_root: Path, *, fmt: str) -> None:
    graph = build_graph(repo_root, load(find_config(repo_root)))
    _print(OrphansCheck().run(graph), fmt)


def list_stale(repo_root: Path, *, fmt: str) -> None:
    graph = build_graph(repo_root, load(find_config(repo_root)))
    _print(StaleReaperCheck().run(graph), fmt)


def list_undocumented(repo_root: Path, *, fmt: str, all_files: bool = False) -> None:
    config = load(find_config(repo_root))
    graph = build_graph(repo_root, config)
    if not all_files:
        findings = [
            f
            for f in UniquenessCheck().run(graph)
            if f.severity == Severity.warning and "no doc claims it" in f.message
        ]
        _print(findings, fmt)
        return

    source_files, _missing = walk_source_files(repo_root, config.paths.source_roots)
    claims = resolve_claims(graph, source_files)
    unclaimed = sorted(
        display
        for _, display in source_files
        if display not in claims and not OMISSION_SKIP.match_file(display)
    )

    # Group by parent directory; directories with the most undocumented files
    # first, so a brownfield adopter knows where to start.
    groups: dict[str, list[str]] = defaultdict(list)
    for source_file in unclaimed:
        groups[str(PurePosixPath(source_file).parent)].append(source_file)
    ordered = sorted(groups.items(), key=lambda item: (-len(item[1]), item[0]))

    if fmt == "json":
        data = [
            {
                "check": "uniqueness",
                "severity": "warning",
                "message": f"source file '{source_file}' has no doc claim",
                "path": source_file,
                "dir": directory,
                "doc_id": None,
            }
            for directory, files in ordered
            for source_file in files
        ]
        typer.echo(json.dumps(data, indent=2))
        return

    for directory, files in ordered:
        typer.echo(f"{directory} ({len(files)} undocumented)")
        for source_file in files:
            typer.echo(f"  {source_file}")
    if not unclaimed:
        typer.echo("(none)")


@dataclass(frozen=True)
class _QueueItem:
    priority: int
    kind: str
    target_path: str
    related_id: str
    reason: str
    suggested_command: str


_PRIORITY_MAP: dict[str, int] = {
    "missing-required-update-path": 1,
    "missing-backlink": 2,
    "no-required-updates-field": 3,
    "broken-implements": 4,
    "stale-claim": 5,
}

_KIND_MAP: dict[str, str] = {
    "missing-required-update-path": "create",
    "missing-backlink": "update",
    "no-required-updates-field": "resolve",
    "broken-implements": "resolve",
    "stale-claim": "update",
}


def _finding_category(f: Finding) -> str:
    return f.category or "other"


def _quote_path(path: str) -> str:
    escaped = path.replace('"', '\\"')
    return f'"{escaped}"'


def _to_queue_item(f: Finding) -> _QueueItem:
    cat = _finding_category(f)
    priority = _PRIORITY_MAP.get(cat, 9)
    kind = _KIND_MAP.get(cat, "resolve")
    target = f.path.as_posix() if f.path else "<repo>"
    related = f.doc_id or ""
    reason = f.message
    cmd = (
        f"irminsul context {_quote_path(target)}"
        if target != "<repo>"
        else "irminsul list lifecycle"
    )
    return _QueueItem(
        priority=priority,
        kind=kind,
        target_path=target,
        related_id=related,
        reason=reason,
        suggested_command=cmd,
    )


def list_lifecycle(repo_root: Path, *, fmt: str, queue: bool) -> None:
    from irminsul.checks.decision_updates import DecisionUpdatesCheck

    graph = build_graph(repo_root, load(find_config(repo_root)))
    findings = DecisionUpdatesCheck().run(graph)

    if not queue:
        _print(findings, fmt)
        return

    items = sorted(
        [_to_queue_item(f) for f in findings],
        key=lambda i: (i.priority, i.target_path),
    )
    if fmt == "json":
        data = [
            {
                "priority": item.priority,
                "kind": item.kind,
                "target_path": item.target_path,
                "related_id": item.related_id,
                "reason": item.reason,
                "suggested_command": item.suggested_command,
            }
            for item in items
        ]
        typer.echo(json.dumps(data, indent=2))
    else:
        for item in items:
            typer.echo(
                f"[{item.priority}:{item.kind}] {item.target_path} "
                f"(re: {item.related_id}) — {item.reason}"
            )
        if not items:
            typer.echo("(none)")


def _print(findings: list[Finding], fmt: str) -> None:
    if fmt == "json":
        data = [
            {
                "check": f.check,
                "severity": f.severity.value,
                "message": f.message,
                "path": f.path.as_posix() if f.path else None,
                "doc_id": f.doc_id,
            }
            for f in findings
        ]
        typer.echo(json.dumps(data, indent=2))
    else:
        for f in findings:
            loc = f.path.as_posix() if f.path else "<repo>"
            typer.echo(f"{loc}: {f.message}")
        if not findings:
            typer.echo("(none)")
