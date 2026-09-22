"""`irminsul list` — enumerate docs by condition."""

from __future__ import annotations

import json
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path, PurePosixPath

import typer

from irminsul.checks.base import Finding, finding_records, fix_commands
from irminsul.checks.globs import walk_configured_source_files
from irminsul.checks.orphans import OrphansCheck
from irminsul.checks.pipeline import run_check
from irminsul.checks.stale_reaper import StaleReaperCheck
from irminsul.checks.uniqueness import (
    UniquenessCheck,
    omitted_from_source_ownership,
    resolve_claims,
)
from irminsul.config import IrminsulConfig, find_config, load
from irminsul.docgraph import DocGraph, build_graph, rfc_nodes

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
        return run_check(OrphansCheck, graph), graph
    if kind == "stale":
        return run_check(StaleReaperCheck, graph), graph
    if kind == "undocumented":
        from irminsul.checks.uniqueness import CODE_UNDOCUMENTED_FILE

        return [f for f in UniquenessCheck().run(graph) if f.code == CODE_UNDOCUMENTED_FILE], graph
    if kind == "lifecycle":
        from irminsul.checks.rfc_follow_through import RfcFollowThroughCheck
        from irminsul.checks.rfc_lifecycle import RfcLifecycleCheck

        lifecycle_categories = set(_PRIORITY_MAP)
        return [
            f
            for f in (*RfcLifecycleCheck().run(graph), *RfcFollowThroughCheck().run(graph))
            if f.category in lifecycle_categories
        ], graph
    raise ValueError(f"unknown list kind '{kind}'; expected one of: {', '.join(LIST_KINDS)}")


def findings_to_json(findings: list[Finding], graph: DocGraph) -> str:
    """The same finding shape `irminsul check --format json` emits.

    `list` wraps checks that implement `fixes()` (notably `rfc-follow-through`
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


def _recorded_debt(repo_root: Path, config: IrminsulConfig) -> set[str]:
    """The adoption record's excepted paths; empty with no record, or an unreadable one."""
    from irminsul.adoption import AdoptionError, load_debt, record_path

    try:
        return set(load_debt(record_path(repo_root, config)))
    except AdoptionError:
        return set()


def list_undocumented(repo_root: Path, *, fmt: str, all_files: bool = False) -> None:
    config = load(find_config(repo_root))
    if not all_files:
        findings, graph = findings_and_graph_for_kind(repo_root, config, "undocumented")
        _print(findings, graph, fmt)
        return

    graph = build_graph(repo_root, config)
    source_files = walk_configured_source_files(repo_root, config).files
    claims = resolve_claims(graph, source_files)
    # Which of these the adoption record already excepts, so a reader can tell the
    # debt somebody signed for from the debt this branch is about to be blamed for.
    debt = _recorded_debt(repo_root, config)
    unclaimed = sorted(
        display
        for _, display in source_files
        if display not in claims and not omitted_from_source_ownership(display, config)
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
                "recorded_debt": source_file in debt,
            }
            for directory, files in ordered
            for source_file in files
        ]
        typer.echo(json.dumps(data, indent=2))
        return

    for directory, files in ordered:
        typer.echo(f"{directory} ({len(files)} undocumented)")
        for source_file in files:
            mark = "  [recorded debt]" if source_file in debt else ""
            typer.echo(f"  {source_file}{mark}")
    if not unclaimed:
        typer.echo("(none)")
    elif debt:
        typer.echo("")
        typer.echo(
            f"{len(debt & set(unclaimed))} of these were already unowned when this "
            "repository adopted Irminsul; the rest are new and fail the gate."
        )


@dataclass(frozen=True)
class _QueueItem:
    priority: int
    kind: str
    target_path: str
    related_id: str
    reason: str
    suggested_command: str


_PRIORITY_MAP: dict[str, int] = {
    "missing-rfc-state": 1,
    "implements-before-implemented": 1,
    "missing-required-update-path": 1,
    "update-missing-implements": 2,
    "no-required-updates-field": 3,
    "broken-implements": 4,
    "dangling-resolved-by": 4,
    "stale-claim": 5,
    "stable-doc-links-draft-rfc": 7,
}

_KIND_MAP: dict[str, str] = {
    "missing-rfc-state": "classify",
    "implements-before-implemented": "finalize",
    "missing-required-update-path": "create",
    "update-missing-implements": "update",
    "no-required-updates-field": "resolve",
    "broken-implements": "resolve",
    "dangling-resolved-by": "resolve",
    "stale-claim": "update",
    "stable-doc-links-draft-rfc": "review-state",
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


def _accepted_backlog_items(config: IrminsulConfig, graph: DocGraph) -> list[_QueueItem]:
    """Accepted-but-not-implemented RFCs and their next mechanical action. Ordering is deterministic document order; priority metadata is
    deliberately out of scope."""
    from irminsul.frontmatter import RfcStateEnum

    out: list[_QueueItem] = []
    for node in rfc_nodes(graph).values():
        state = node.frontmatter.rfc_state
        if state is None or state != RfcStateEnum.accepted:
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


def _shipped_draft_items(
    repo_root: Path, config: IrminsulConfig, graph: DocGraph
) -> list[_QueueItem]:
    from irminsul.code_references import CodeResolver
    from irminsul.frontmatter import RfcStateEnum
    from irminsul.inventory import kind_capabilities
    from irminsul.listing.review import shipped_draft_evidence

    drafts = [
        node
        for node in rfc_nodes(graph).values()
        if node.frontmatter.rfc_state is not None
        and node.frontmatter.rfc_state == RfcStateEnum.draft
    ]
    if not drafts:
        return []
    resolver = CodeResolver(repo_root, config)
    foreign = frozenset(
        flag
        for node in graph.nodes.values()
        for entry in node.frontmatter.inventory
        if kind_capabilities(entry.kind, config).mention_patterns
        for flag in entry.foreign
    )
    out: list[_QueueItem] = []
    for node in drafts:
        evidence = shipped_draft_evidence(resolver, node, foreign)
        if evidence is None:
            continue
        out.append(
            _QueueItem(
                priority=8,
                kind="review-shipped",
                target_path=node.path.as_posix(),
                related_id=node.id,
                reason=(
                    "draft RFC names only identities that already exist: " + ", ".join(evidence)
                ),
                suggested_command=f"irminsul change status {node.id}",
            )
        )
    return out


def list_lifecycle(repo_root: Path, *, fmt: str, queue: bool) -> None:
    config = load(find_config(repo_root))
    findings, graph = findings_and_graph_for_kind(repo_root, config, "lifecycle")

    if not queue:
        _print(findings, graph, fmt)
        # An accepted RFC nobody has implemented is unfinished lifecycle work, but it
        # raises no finding until a threshold elapses, so a plain listing used to say
        # "(none)" over a backlog years deep.
        waiting = _accepted_backlog_items(config, graph)
        if waiting and fmt != "json":
            typer.echo(
                f"\n{len(waiting)} accepted RFC(s) awaiting implementation; "
                f"run `irminsul list lifecycle --queue` for the work they imply:"
            )
            for item in waiting:
                typer.echo(f"  {item.target_path}")
        return

    items = sorted(
        [_to_queue_item(f) for f in findings]
        + _accepted_backlog_items(config, graph)
        + _shipped_draft_items(repo_root, config, graph),
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


def list_baseline(repo_root: Path, *, fmt: str) -> None:
    """Every baseline entry, and whether it still hides a finding or is fixed."""
    from irminsul.baseline import BaselineError, finding_fingerprint, load_entries
    from irminsul.checks.pipeline import enabled_findings

    config = load(find_config(repo_root))
    path = repo_root / config.paths.baseline
    try:
        entries = load_entries(path) if path.is_file() else []
    except BaselineError as e:
        typer.echo(typer.style(str(e), fg="red"))
        raise typer.Exit(code=2) from None
    live = {
        finding_fingerprint(finding)
        for finding in enabled_findings(build_graph(repo_root, config), baseline=False)
    }
    rows = [
        {
            "state": "hidden" if entry.fingerprint in live else "fixed",
            "check": entry.check,
            "path": entry.path or None,
            "message": entry.message,
        }
        for entry in entries
    ]
    if fmt == "json":
        typer.echo(json.dumps({"path": config.paths.baseline, "entries": rows}, indent=2))
        return
    if not path.is_file():
        typer.echo(f"(no baseline at {config.paths.baseline})")
        return
    for row in rows:
        typer.echo(
            f"{row['state']:<7} [{row['check']}] {row['path'] or '(repository)'}: {row['message']}"
        )
    fixed = sum(row["state"] == "fixed" for row in rows)
    typer.echo(
        f"{len(rows) - fixed} hidden, {fixed} fixed"
        + ("; run irminsul check --update-baseline to remove the fixed entries" if fixed else "")
    )
