"""First-party MCP server: the doc graph as native tools for AI agents.

Two layers, deliberately separated:

- Plain ``*_json`` functions take ``(repo_root, config, ...)`` and return the
  exact JSON strings the CLI's ``--format json`` already produces. They do not
  depend on the MCP SDK and are what tests exercise.
- :func:`create_server` wraps them in an ``MCPServer`` stdio server. It is the
  only place the optional ``mcp`` package is imported (install via
  ``pip install 'irminsul[mcp]'``).

The server is strictly read-only: no tool writes files. Config is re-read on
every tool call so a long-running server sees edits made between calls. Its own
code is not: Python imported it once, so a call made after the package changed on
disk is refused rather than answered from the old code.
"""

from __future__ import annotations

import functools
from collections.abc import Callable
from pathlib import Path
from typing import TYPE_CHECKING, ParamSpec

import irminsul
from irminsul.checks import sort_findings
from irminsul.checks.claim_anchor import ClaimAnchorCheck
from irminsul.checks.pipeline import run_check, run_checks
from irminsul.checks.render import findings_json
from irminsul.config import IrminsulConfig, find_config, load
from irminsul.context import build_context_report, context_report_to_json
from irminsul.docgraph import build_graph
from irminsul.errors import UserError
from irminsul.listing.command import list_json
from irminsul.orient import build_orient_report, orient_report_to_json
from irminsul.refs import build_doc_refs_report, doc_refs_report_to_json
from irminsul.surface import derive_requested_surface, surface_items_to_json

if TYPE_CHECKING:  # pragma: no cover - typing only; `mcp` is an optional extra
    from mcp.server import MCPServer

PACKAGE_DIR = Path(irminsul.__file__).parent

_MAX_NAMED_CHANGES = 3

CodeFingerprint = tuple[tuple[str, int, int], ...]

P = ParamSpec("P")

SERVER_INSTRUCTIONS = (
    "Query this repository's Irminsul doc graph. Every tool is read-only, "
    "deterministic, and returns the same JSON the irminsul CLI prints with "
    "--format json. Call `orient` first to learn the docs layout, configured "
    "checks, and which tool to use when."
)


def orient_json(repo_root: Path, config: IrminsulConfig) -> str:
    """One-shot orientation report (`irminsul orient`), as JSON."""
    return orient_report_to_json(build_orient_report(repo_root, config))


def context_for_path_json(repo_root: Path, config: IrminsulConfig, paths: list[str]) -> str:
    """The packet `irminsul context <path...>` prints for these paths, as JSON."""
    report = build_context_report(repo_root, config, target_paths=[Path(path) for path in paths])
    return context_report_to_json(report)


def context_for_topic_json(repo_root: Path, config: IrminsulConfig, query: str) -> str:
    """Context report for a deterministic substring topic search, as JSON."""
    report = build_context_report(repo_root, config, topic=query)
    return context_report_to_json(report)


def context_after_edit_json(
    repo_root: Path,
    config: IrminsulConfig,
    base_ref: str | None = None,
    committed_only: bool = False,
) -> str:
    """The `irminsul context --after-edit` report, as JSON."""
    report = build_context_report(
        repo_root, config, after_edit=True, base_ref=base_ref, committed_only=committed_only
    )
    return context_report_to_json(report)


def refs_json(repo_root: Path, config: IrminsulConfig, target: str) -> str:
    """The strong and weak inbound references of a doc id or path (`irminsul refs`), as
    JSON. A target that names no doc raises `RefsError` rather than answering a
    different question."""
    graph = build_graph(repo_root, config)
    return doc_refs_report_to_json(build_doc_refs_report(repo_root, graph, target))


def check_json(repo_root: Path, config: IrminsulConfig, only: list[str] | None = None) -> str:
    """Run the enabled checks, or the registered checks `only` names, as JSON.

    The run plain `irminsul check --only` makes, printed by the same `findings_json`: the
    shared run, ignore-comment audit and baseline included, so its findings, its `baseline`
    report and its `adoption` assessment are the CLI's. A baseline file that does not load
    raises `BaselineError`, as the CLI exits 2 on it. No `--diff` range and no `--delta` are
    applied.
    """
    graph = build_graph(repo_root, config)
    result = run_checks(graph, only=only)
    return findings_json(result.findings, graph, run=result)


def list_docs_json(repo_root: Path, config: IrminsulConfig, kind: str) -> str:
    """One `irminsul list` subcommand's JSON; an unknown kind raises `UnknownListKindError`
    naming every kind."""
    return list_json(repo_root, config, kind)


def surface_json(
    repo_root: Path,
    config: IrminsulConfig,
    kind: str,
    source_glob: str | None = None,
) -> str:
    """Derive a live code surface (`irminsul surface <kind>`), as JSON."""
    return surface_items_to_json(derive_requested_surface(repo_root, config, kind, source_glob))


def anchors_json(repo_root: Path, config: IrminsulConfig) -> str:
    """Anchored prose-claim report (`irminsul anchors`), as JSON."""
    graph = build_graph(repo_root, config)
    findings = sort_findings(run_check(ClaimAnchorCheck, graph))
    return findings_json(findings, graph)


def change_status_json(repo_root: Path, config: IrminsulConfig, change: str) -> str:
    """Change lifecycle report (`irminsul change status`), as JSON."""
    from irminsul.change.report import build_change_report, change_report_to_json

    return change_report_to_json(build_change_report(repo_root, config, change, next_step=True))


def change_verify_json(
    repo_root: Path,
    config: IrminsulConfig,
    change: str,
    base_ref: str | None = None,
    committed_only: bool = False,
) -> str:
    """Full readiness report (`irminsul change verify`), as JSON."""
    from irminsul.change.report import build_change_report, change_report_to_json

    return change_report_to_json(
        build_change_report(
            repo_root, config, change, base_ref=base_ref, committed_only=committed_only
        )
    )


def code_fingerprint(package_dir: Path) -> CodeFingerprint:
    """Every `*.py` under `package_dir` as (package-relative POSIX path, mtime ns, size), sorted."""
    entries: list[tuple[str, int, int]] = []
    for path in package_dir.rglob("*.py"):
        try:
            stat = path.stat()
        except FileNotFoundError:
            continue
        entries.append((path.relative_to(package_dir).as_posix(), stat.st_mtime_ns, stat.st_size))
    return tuple(sorted(entries))


def _code_changes(loaded: CodeFingerprint, current: CodeFingerprint) -> list[str]:
    before = {path: (mtime, size) for path, mtime, size in loaded}
    after = {path: (mtime, size) for path, mtime, size in current}
    changes: dict[str, str] = {}
    for path in before.keys() | after.keys():
        if path not in after:
            changes[path] = "removed"
        elif path not in before:
            changes[path] = "added"
        elif before[path] != after[path]:
            changes[path] = "modified"
    return [f"{path} ({changes[path]})" for path in sorted(changes)]


def stale_code_message(package_dir: Path, loaded: CodeFingerprint) -> str | None:
    """The refusal a server owes when `package_dir` no longer matches the code it loaded,
    or None while it does."""
    changes = _code_changes(loaded, code_fingerprint(package_dir))
    if not changes:
        return None
    named = ", ".join(changes[:_MAX_NAMED_CHANGES])
    if len(changes) > _MAX_NAMED_CHANGES:
        named += f" and {len(changes) - _MAX_NAMED_CHANGES} more"
    return (
        f"irminsul's code changed on disk since this server started: {named}. Every call is "
        "refused rather than answered from outdated code. Reconnect the server to load the "
        "current code (in Claude Code: /mcp, then reconnect irminsul). Until then, run the "
        "same query through the CLI, for example `irminsul orient --format json`."
    )


def create_server(repo_root: Path) -> MCPServer:
    """Build the MCPServer stdio server exposing the read-only tool set."""
    from mcp.server import MCPServer
    from mcp.server.mcpserver.exceptions import ToolError

    root = repo_root.resolve()
    package_dir = PACKAGE_DIR
    loaded = code_fingerprint(package_dir)

    def guarded(tool: Callable[P, str]) -> Callable[P, str]:
        """Wrap a tool so it refuses when the code changed, and so the errors the CLI turns
        into a message reach the agent as one. The SDK withholds the text of any other
        exception, so a `ToolError` is the only way to explain a refusal."""

        @functools.wraps(tool)
        def run(*args: P.args, **kwargs: P.kwargs) -> str:
            message = stale_code_message(package_dir, loaded)
            if message is not None:
                raise ToolError(message)
            try:
                return tool(*args, **kwargs)
            except UserError as exc:
                raise ToolError(str(exc)) from exc

        return run

    def _config() -> IrminsulConfig:
        return load(find_config(root))

    server = MCPServer("irminsul", instructions=SERVER_INSTRUCTIONS)

    @server.tool()
    @guarded
    def orient() -> str:
        """Call first in an unfamiliar repo: returns the docs layout, doc counts by layer and status, how much of the source a doc owns, entry docs, configured checks, and a command vocabulary."""
        return orient_json(root, _config())

    @server.tool()
    @guarded
    def context_for_path(paths: list[str]) -> str:
        """Call before editing source or doc files to get each one's owning doc, source claims, tests, dependencies, active RFCs, claims to read, and excerpts. For a source file, `tests` is ranked: the tests that import it come first, then those that changed with it, and `test_reasons` says why each of those is named. Runs no checks; call `check` or `context_after_edit` for findings."""
        return context_for_path_json(root, _config(), paths)

    @server.tool()
    @guarded
    def context_for_topic(query: str) -> str:
        """Call when you know a concept but not a file path: substring-searches doc ids, titles, paths, describes, tests, tags, summaries, and headings for matching docs, ranking a metadata match above one only a heading holds. Every whitespace-separated term must match. An empty result carries a `suggestion` naming the fields searched and what to try next."""
        return context_for_topic_json(root, _config(), query)

    @server.tool()
    @guarded
    def context_after_edit(base_ref: str | None = None, committed_only: bool = False) -> str:
        """Call after editing: maps the change to its owning docs, runs the enabled checks, and reports what the repository fails on and what this change introduced. `base_ref` is the branch point to measure against, such as origin/main (IRMINSUL_BASE_REF or GITHUB_BASE_REF when not given): the change then runs from its merge base to the working tree, so committed and uncommitted work both count and the passes `check --diff` adds run too. Without a base the working tree is compared with HEAD, which says nothing about work already committed, and those passes do not run. `committed_only` leaves staged, unstaged and untracked work out; with no base the change is empty, so nothing is judged as one."""
        return context_after_edit_json(root, _config(), base_ref, committed_only)

    @server.tool()
    @guarded
    def refs(target: str) -> str:
        """Call to gauge blast radius before renaming or moving a doc: returns the docs that depend on or link to a doc id or path. A target that names no doc is an error."""
        return refs_json(root, _config(), target)

    @server.tool()
    @guarded
    def check(only: list[str] | None = None) -> str:
        """Call after editing code or docs to run the checks enabled in irminsul.toml; returns the findings plain `irminsul check` reports, each with its class, plus a summary, the `baseline` report of what the repository's baseline hid and, where the repository has an adoption record, the `adoption` report of the ownership debt it excepts. `only` names registered checks to run instead, whether or not they are enabled. This is not the pull-request gate: the passes `irminsul check --diff origin/<base>` adds do not run, and neither does `--delta`."""
        return check_json(root, _config(), only)

    @server.tool()
    @guarded
    def list_docs(kind: str) -> str:
        """Call to find documentation debt: kind is 'undocumented', 'lifecycle', or 'review' (sentences that name code, paired with that code, for semantic review). For one check's findings, call `check` with `only`."""
        return list_docs_json(root, _config(), kind)

    @server.tool()
    @guarded
    def surface(kind: str, source_glob: str | None = None) -> str:
        """Call to see what the code actually exposes right now: derives a live surface of a built-in or configured kind from source; an unknown kind's error names the built-ins. `source_glob` is a gitignore-style pattern matched against source paths as irminsul displays them (repo-relative, or source-root-relative for a separate code repository) and limits extraction to matching files."""
        return surface_json(root, _config(), kind, source_glob)

    @server.tool()
    @guarded
    def anchors() -> str:
        """Call to audit anchored prose claims: flags claims whose pinned code symbol changed since the prose was last verified. Read-only; re-pinning stays a deliberate human CLI action."""
        return anchors_json(root, _config())

    @server.tool()
    @guarded
    def change_status(change: str) -> str:
        """Call to orient on one RFC: lifecycle state, declared scope, task evidence, blockers, and valid next transitions. `change` is the RFC's doc id or repo-relative path. Lifecycle writes stay confirmed CLI actions (`irminsul change transition/finalize`)."""
        return change_status_json(root, _config(), change)

    @server.tool()
    @guarded
    def change_verify(
        change: str, base_ref: str | None = None, committed_only: bool = False
    ) -> str:
        """Call before proposing acceptance or finalization: full mechanical-readiness report with blockers, evidence, and semantic-review clues. `change` is the RFC's doc id or repo-relative path; `base_ref` is the git ref to compare against, such as origin/main, and the change runs from its merge base to the working tree, so uncommitted work counts unless `committed_only` leaves it out (with no base the change is empty). Inspect the evidence paths, then ask the user to run the confirmed CLI transition (`irminsul change transition` or `irminsul change finalize`, which refuses a tree with uncommitted work)."""
        return change_verify_json(root, _config(), change, base_ref, committed_only)

    return server
