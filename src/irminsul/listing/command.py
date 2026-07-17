"""`irminsul list` — enumerate docs by condition."""

from __future__ import annotations

import json
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path, PurePosixPath

import typer

from irminsul.checks.base import Finding, Severity, finding_records, fix_commands
from irminsul.checks.globs import walk_configured_source_files
from irminsul.checks.orphans import OrphansCheck
from irminsul.checks.stale_reaper import StaleReaperCheck
from irminsul.checks.uniqueness import OMISSION_SKIP, UniquenessCheck, resolve_claims
from irminsul.config import IrminsulConfig, find_config, load
from irminsul.docgraph import DocGraph, build_graph

LIST_KINDS = ("orphans", "stale", "undocumented", "lifecycle")


def findings_and_graph_for_kind(
    repo_root: Path, config: IrminsulConfig, kind: str
) -> tuple[list[Finding], DocGraph]:
    """The findings behind one `irminsul list` subcommand, plus the graph they came from.

    The graph is returned because the shared findings serializer needs it to
    decide whether `irminsul fix` would remediate each finding, and because
    `list lifecycle` reuses it to derive the accepted-RFC backlog.
    """
    graph = build_graph(repo_root, config)
    if kind == "orphans":
        return OrphansCheck().run(graph), graph
    if kind == "stale":
        return StaleReaperCheck().run(graph), graph
    if kind == "undocumented":
        return [
            f
            for f in UniquenessCheck().run(graph)
            if f.severity == Severity.warning and "no doc claims it" in f.message
        ], graph
    if kind == "lifecycle":
        from irminsul.checks.decision_updates import DecisionUpdatesCheck
        from irminsul.checks.rfc_lifecycle_integrity import RfcLifecycleIntegrityCheck

        return [
            *DecisionUpdatesCheck().run(graph),
            *RfcLifecycleIntegrityCheck().run(graph),
        ], graph
    raise ValueError(f"unknown list kind '{kind}'; expected one of: {', '.join(LIST_KINDS)}")


def findings_to_json(findings: list[Finding], graph: DocGraph) -> str:
    """The same finding shape `irminsul check --format json` emits.

    `list` wraps checks that implement `fixes()` (notably `decision-updates`
    behind `lifecycle`), so hiding `data`/`fixable` here would make the one
    findings surface that lies about fixability. The fix commands name the
    `all-available` profile because `list` selects its checks regardless of
    what `irminsul.toml` activates.
    """
    commands = fix_commands(findings, graph, profile="all-available")
    return json.dumps(finding_records(findings, commands), indent=2)


def list_orphans(repo_root: Path, *, fmt: str) -> None:
    findings, graph = findings_and_graph_for_kind(
        repo_root, load(find_config(repo_root)), "orphans"
    )
    _print(findings, graph, fmt)


def list_stale(repo_root: Path, *, fmt: str) -> None:
    findings, graph = findings_and_graph_for_kind(repo_root, load(find_config(repo_root)), "stale")
    _print(findings, graph, fmt)


def list_undocumented(repo_root: Path, *, fmt: str, all_files: bool = False) -> None:
    config = load(find_config(repo_root))
    if not all_files:
        findings, graph = findings_and_graph_for_kind(repo_root, config, "undocumented")
        _print(findings, graph, fmt)
        return

    graph = build_graph(repo_root, config)
    source_files = walk_configured_source_files(repo_root, config).files
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
    "frozen-content-changed": 1,
    "premature-frozen-hash": 1,
    "implementation-evidence-before-finalization": 1,
    "missing-frozen-hash": 6,
    "stable-doc-links-draft-rfc": 7,
    "pre-lifecycle-rfc": 6,
}

_KIND_MAP: dict[str, str] = {
    "missing-required-update-path": "create",
    "missing-backlink": "update",
    "no-required-updates-field": "resolve",
    "broken-implements": "resolve",
    "stale-claim": "update",
    "frozen-content-changed": "supersede",
    "premature-frozen-hash": "resolve",
    "implementation-evidence-before-finalization": "finalize",
    "missing-frozen-hash": "freeze",
    "stable-doc-links-draft-rfc": "review-state",
    "pre-lifecycle-rfc": "migrate",
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
    if cat == "pre-lifecycle-rfc" and related:
        cmd = f"irminsul change migrate {related}"
    else:
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


def _accepted_backlog_items(config: IrminsulConfig, graph: DocGraph) -> list[_QueueItem]:
    """Accepted-but-not-implemented RFCs and their next mechanical action
    (RFC 0034). Ordering is deterministic document order; priority metadata is
    deliberately out of scope."""
    from irminsul.frontmatter import RfcStateEnum, canonical_rfc_state

    docs_root = (config.paths.docs_root or "docs").replace("\\", "/").strip("/")
    rfc_prefix = f"{docs_root}/80-evolution/rfcs/"

    out: list[_QueueItem] = []
    for node in graph.nodes.values():
        if not node.path.as_posix().startswith(rfc_prefix):
            continue
        state = node.frontmatter.rfc_state
        if state is None or canonical_rfc_state(state) != RfcStateEnum.accepted:
            continue
        out.append(
            _QueueItem(
                priority=6,
                kind="implement",
                target_path=node.path.as_posix(),
                related_id=node.id,
                reason="accepted RFC is not yet implemented",
                suggested_command=f"irminsul change status {node.id}",
            )
        )
    return out


def list_lifecycle(repo_root: Path, *, fmt: str, queue: bool) -> None:
    config = load(find_config(repo_root))
    findings, graph = findings_and_graph_for_kind(repo_root, config, "lifecycle")

    if not queue:
        _print(findings, graph, fmt)
        return

    items = sorted(
        [_to_queue_item(f) for f in findings] + _accepted_backlog_items(config, graph),
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


def _print(findings: list[Finding], graph: DocGraph, fmt: str) -> None:
    if fmt == "json":
        typer.echo(findings_to_json(findings, graph))
    else:
        for f in findings:
            loc = f.path.as_posix() if f.path else "<repo>"
            typer.echo(f"{loc}: {f.message}")
        if not findings:
            typer.echo("(none)")
