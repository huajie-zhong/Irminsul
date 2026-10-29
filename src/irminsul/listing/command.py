"""`irminsul list` — enumerate docs by condition."""

from __future__ import annotations

import json
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path, PurePosixPath

import typer

from irminsul.adoption import recorded_debt
from irminsul.checks.base import Finding, finding_records
from irminsul.checks.pipeline import run_check
from irminsul.checks.rfc_follow_through import (
    CODE_MISSING_REQUIRED_UPDATE_PATH,
    CODE_NO_REQUIRED_UPDATES_FIELD,
    CODE_STABLE_DOC_LINKS_DRAFT_RFC,
    CODE_STALE_CLAIM,
    CODE_UPDATE_MISSING_IMPLEMENTS,
    RfcFollowThroughCheck,
)
from irminsul.checks.rfc_lifecycle import (
    CODE_BROKEN_IMPLEMENTS,
    CODE_DANGLING_RESOLVED_BY,
    CODE_IMPLEMENTS_BEFORE_IMPLEMENTED,
    CODE_MISSING_RFC_STATE,
    RfcLifecycleCheck,
)
from irminsul.checks.uniqueness import UniquenessCheck, source_ownership
from irminsul.config import IrminsulConfig
from irminsul.docgraph import DocGraph, build_graph, rfc_nodes
from irminsul.errors import UserError

LIST_KINDS = ("undocumented", "lifecycle", "review")


class UnknownListKindError(UserError, ValueError):
    """A list kind that is not one of `LIST_KINDS`."""


def list_json(repo_root: Path, config: IrminsulConfig, kind: str) -> str:
    if kind == "review":
        from irminsul.listing.review import review_json

        return review_json(repo_root, config)
    findings, graph = findings_and_graph_for_kind(repo_root, config, kind)
    return findings_to_json(findings, graph)


def findings_and_graph_for_kind(
    repo_root: Path, config: IrminsulConfig, kind: str
) -> tuple[list[Finding], DocGraph]:
    """The findings behind one `irminsul list` subcommand, plus the graph they came from.

    The graph is returned because the shared findings serializer needs it to
    decide whether `irminsul fix` would remediate each finding, and because
    `list lifecycle` reuses it to derive the accepted-RFC backlog.
    """
    graph = build_graph(repo_root, config)
    if kind == "undocumented":
        from irminsul.checks.uniqueness import CODE_UNDOCUMENTED_FILE

        undocumented = run_check(UniquenessCheck, graph)
        return [f for f in undocumented if f.code == CODE_UNDOCUMENTED_FILE], graph
    if kind == "lifecycle":
        return [
            f
            for f in (
                *run_check(RfcLifecycleCheck, graph),
                *run_check(RfcFollowThroughCheck, graph),
            )
            if f.code in _PRIORITY_MAP
        ], graph
    raise UnknownListKindError(
        f"unknown list kind '{kind}'; expected one of: {', '.join(LIST_KINDS)}"
    )


def findings_to_json(findings: list[Finding], graph: DocGraph) -> str:
    """The same finding shape `irminsul check --format json` emits.

    `list` wraps checks that implement `fixes()` (notably `rfc-follow-through`
    behind `lifecycle`), so hiding `data`/`fixable` here would make the one
    findings surface that lies about fixability.
    """
    return json.dumps(finding_records(findings, graph), indent=2)


def list_undocumented(
    repo_root: Path, config: IrminsulConfig, *, fmt: str, all_files: bool = False
) -> None:
    if not all_files:
        findings, graph = findings_and_graph_for_kind(repo_root, config, "undocumented")
        _print(findings, graph, fmt)
        return

    graph = build_graph(repo_root, config)
    _, unclaimed = source_ownership(graph)
    # Which of these the adoption record already excepts, so a reader can tell the
    # debt somebody signed for from the debt this branch is about to be blamed for.
    debt = recorded_debt(graph) or frozenset()

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
    CODE_MISSING_RFC_STATE: 1,
    CODE_IMPLEMENTS_BEFORE_IMPLEMENTED: 1,
    CODE_MISSING_REQUIRED_UPDATE_PATH: 1,
    CODE_UPDATE_MISSING_IMPLEMENTS: 2,
    CODE_NO_REQUIRED_UPDATES_FIELD: 3,
    CODE_BROKEN_IMPLEMENTS: 4,
    CODE_DANGLING_RESOLVED_BY: 4,
    CODE_STALE_CLAIM: 5,
    CODE_STABLE_DOC_LINKS_DRAFT_RFC: 7,
}

_KIND_MAP: dict[str, str] = {
    CODE_MISSING_RFC_STATE: "classify",
    CODE_IMPLEMENTS_BEFORE_IMPLEMENTED: "finalize",
    CODE_MISSING_REQUIRED_UPDATE_PATH: "create",
    CODE_UPDATE_MISSING_IMPLEMENTS: "update",
    CODE_NO_REQUIRED_UPDATES_FIELD: "resolve",
    CODE_BROKEN_IMPLEMENTS: "resolve",
    CODE_DANGLING_RESOLVED_BY: "resolve",
    CODE_STALE_CLAIM: "update",
    CODE_STABLE_DOC_LINKS_DRAFT_RFC: "review-state",
}


def _quote_path(path: str) -> str:
    escaped = path.replace('"', '\\"')
    return f'"{escaped}"'


def _to_queue_item(f: Finding) -> _QueueItem:
    priority = _PRIORITY_MAP.get(f.code, 9)
    kind = _KIND_MAP.get(f.code, "resolve")
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
    """Accepted-but-not-implemented RFCs and their next mechanical action, in document
    order."""
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
    """Draft RFCs whose code spans name at least two live identities and nothing absent.

    That is evidence the proposal may already have shipped, never a recommended state.
    Flags a `cli-options` entry lists as `foreign` do not count.
    """
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
    resolver = CodeResolver(graph.source)
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


def list_lifecycle(repo_root: Path, config: IrminsulConfig, *, fmt: str, queue: bool) -> None:
    findings, graph = findings_and_graph_for_kind(repo_root, config, "lifecycle")

    if not queue:
        _print(findings, graph, fmt)
        # An accepted RFC nobody has implemented is unfinished lifecycle work, but it
        # raises no finding until a threshold elapses, so a plain listing would say
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


def list_baseline(repo_root: Path, config: IrminsulConfig, *, fmt: str) -> None:
    """Every baseline entry, and whether it still hides a finding or is fixed.

    Raises `BaselineError` for a baseline that cannot be read.
    """
    from irminsul.baseline import finding_fingerprint, load_entries
    from irminsul.checks.pipeline import run_checks

    path = repo_root / config.paths.baseline
    entries = load_entries(path) if path.is_file() else []
    # Hidden is what the run's own baseline step hid, so an entry the baseline rule refuses
    # to honour reads as fixed here exactly as `check` counts it stale.
    live = {
        finding_fingerprint(finding)
        for finding in run_checks(build_graph(repo_root, config)).hidden
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
        + ("; run irminsul baseline update to remove the fixed entries" if fixed else "")
    )
