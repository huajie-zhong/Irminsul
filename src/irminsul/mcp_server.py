"""First-party MCP server: the doc graph as native tools for AI agents.

Two layers, deliberately separated:

- Plain ``*_json`` functions take ``(repo_root, config, ...)`` and return the
  exact JSON strings the CLI's ``--format json`` already produces. They do not
  depend on the MCP SDK and are what tests exercise.
- :func:`create_server` wraps them in a FastMCP stdio server. It is the only
  place the optional ``mcp`` package is imported (install via
  ``pip install 'irminsul[mcp]'``).

The server is strictly read-only: no tool writes files. Config is re-read on
every tool call so a long-running server sees edits made between calls.
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from irminsul.checks import HARD_REGISTRY, SOFT_REGISTRY, Check, Finding, sort_findings, summarize
from irminsul.checks.claim_anchor import ClaimAnchorCheck
from irminsul.config import IrminsulConfig, find_config, load
from irminsul.context import build_context_report, context_report_to_json
from irminsul.docgraph import build_graph
from irminsul.listing.command import findings_for_kind, findings_to_json
from irminsul.orient import build_orient_report, orient_report_to_json
from irminsul.refs import (
    RefsError,
    build_doc_refs_report,
    build_symbol_refs_report,
    doc_refs_report_to_json,
    symbol_refs_report_to_json,
)
from irminsul.surface import derive_surface, surface_items_to_json

if TYPE_CHECKING:  # pragma: no cover - typing only; `mcp` is an optional extra
    from mcp.server.fastmcp import FastMCP

CHECK_PROFILES = ("hard", "configured")

SERVER_INSTRUCTIONS = (
    "Query this repository's Irminsul doc graph. Every tool is read-only, "
    "deterministic, and returns the same JSON the irminsul CLI prints with "
    "--format json. Call `orient` first to learn the docs layout, configured "
    "checks, and which tool to use when."
)


def orient_json(repo_root: Path, config: IrminsulConfig) -> str:
    """One-shot orientation report (`irminsul orient`), as JSON."""
    return orient_report_to_json(build_orient_report(repo_root, config))


def context_for_path_json(repo_root: Path, config: IrminsulConfig, path: str) -> str:
    """Context report for one source or doc path, as JSON."""
    report = build_context_report(repo_root, config, target_path=Path(path))
    return context_report_to_json(report)


def context_for_topic_json(repo_root: Path, config: IrminsulConfig, query: str) -> str:
    """Context report for a deterministic substring topic search, as JSON."""
    report = build_context_report(repo_root, config, topic=query)
    return context_report_to_json(report)


def context_changed_json(repo_root: Path, config: IrminsulConfig) -> str:
    """Context report for the current git staged/unstaged/untracked files, as JSON."""
    report = build_context_report(repo_root, config, changed=True)
    return context_report_to_json(report)


def refs_json(repo_root: Path, config: IrminsulConfig, target: str) -> str:
    """Backlinks for a doc id/path, falling back to symbol references, as JSON.

    Mirrors `irminsul refs`: if `target` resolves to a doc, return its strong
    and weak inbound references; otherwise treat it as a code symbol and return
    owning docs and claim references.
    """
    graph = build_graph(repo_root, config)
    try:
        return doc_refs_report_to_json(build_doc_refs_report(repo_root, graph, target))
    except RefsError:
        return symbol_refs_report_to_json(build_symbol_refs_report(graph, target, repo_root))


def check_json(repo_root: Path, config: IrminsulConfig, profile: str = "hard") -> str:
    """Run the registered deterministic checks for `profile`, as JSON.

    Same selection as `irminsul check`, restricted to the `hard` and
    `configured` profiles — LLM checks are never run over MCP. Unknown check
    names from config are skipped silently (the CLI prints a note instead).
    """
    if profile not in CHECK_PROFILES:
        raise ValueError(
            f"unknown check profile '{profile}'; expected one of: {', '.join(CHECK_PROFILES)}"
        )

    # The name-selection and JSON shape are owned by the CLI module; reuse them
    # rather than duplicating the logic here.
    from irminsul.cli import Profile, _findings_to_json, _hard_check_names, _soft_check_names

    prof = Profile(profile)
    graph = build_graph(repo_root, config)
    selected: list[tuple[str, dict[str, type[Check]]]] = [
        *[(name, HARD_REGISTRY) for name in _hard_check_names(prof, config)],
        *[(name, SOFT_REGISTRY) for name in _soft_check_names(prof, config)],
    ]

    findings: list[Finding] = []
    for check_name, registry in selected:
        cls = registry.get(check_name)
        if cls is None:
            continue
        findings.extend(cls().run(graph))

    findings = sort_findings(findings)
    return _findings_to_json(findings, summarize(findings))


def list_docs_json(repo_root: Path, config: IrminsulConfig, kind: str) -> str:
    """Findings behind one `irminsul list` subcommand, as JSON.

    Kind validation lives in `findings_for_kind`, which raises ValueError for
    unknown kinds — no second copy of the check here.
    """
    return findings_to_json(findings_for_kind(repo_root, config, kind))


def surface_json(
    repo_root: Path,
    config: IrminsulConfig,
    kind: str,
    source_glob: str | None = None,
) -> str:
    """Derive a live code surface (`irminsul surface <kind>`), as JSON."""
    from irminsul.inventory import get_extractor

    if get_extractor(kind, config) is None:
        raise ValueError(
            f"no extractor for kind '{kind}' "
            "(built-in: cli, http, exports, env-vars, mcp; or declare a generic rule)"
        )
    return surface_items_to_json(derive_surface(repo_root, config, kind, source_glob))


def anchors_json(repo_root: Path, config: IrminsulConfig) -> str:
    """Anchored prose-claim report (`irminsul anchors`), as JSON."""
    from irminsul.cli import _findings_to_json

    graph = build_graph(repo_root, config)
    findings = sort_findings(ClaimAnchorCheck().run(graph))
    return _findings_to_json(findings, summarize(findings))


def create_server(repo_root: Path) -> FastMCP:
    """Build the FastMCP stdio server exposing the read-only tool set."""
    from mcp.server.fastmcp import FastMCP

    root = repo_root.resolve()

    def _config() -> IrminsulConfig:
        return load(find_config(root))

    server = FastMCP("irminsul", instructions=SERVER_INSTRUCTIONS)

    @server.tool()
    def orient() -> str:
        """Call FIRST in an unfamiliar repo: returns the docs layout, doc counts by layer and status, entry docs, configured checks, and a command vocabulary."""
        return orient_json(root, _config())

    @server.tool()
    def context_for_path(path: str) -> str:
        """Call before editing a specific source or doc file to get its owning doc, source claims, tests, dependencies, and open findings."""
        return context_for_path_json(root, _config(), path)

    @server.tool()
    def context_for_topic(query: str) -> str:
        """Call when you know a concept but not a file path: substring-searches doc ids, titles, paths, describes, and tests for matching docs."""
        return context_for_topic_json(root, _config(), query)

    @server.tool()
    def context_changed() -> str:
        """Call before committing to map the current git staged, unstaged, and untracked files to their owning docs and relevant findings."""
        return context_changed_json(root, _config())

    @server.tool()
    def refs(target: str) -> str:
        """Call to gauge blast radius before renaming or editing: returns docs referencing a doc id/path, or owners and references of a code symbol."""
        return refs_json(root, _config(), target)

    @server.tool()
    def check(profile: str = "hard") -> str:
        """Call after editing docs to verify the tree still passes deterministic checks ('hard' or 'configured'); returns findings plus a summary."""
        return check_json(root, _config(), profile)

    @server.tool()
    def list_docs(kind: str) -> str:
        """Call to find documentation debt: kind is 'orphans', 'stale', 'undocumented', or 'lifecycle'."""
        return list_docs_json(root, _config(), kind)

    @server.tool()
    def surface(kind: str, source_glob: str | None = None) -> str:
        """Call to see what the code actually exposes right now: derives the live 'cli', 'http', 'exports', or 'env-vars' surface from source."""
        return surface_json(root, _config(), kind, source_glob)

    @server.tool()
    def anchors() -> str:
        """Call to audit anchored prose claims: flags claims whose pinned code symbol changed since the prose was last verified. Read-only; re-pinning stays a deliberate human CLI action."""
        return anchors_json(root, _config())

    return server
