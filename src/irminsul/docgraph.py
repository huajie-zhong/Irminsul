"""Build the in-memory `DocGraph` for a codebase.

Walks `docs_root` from the config, parses every `*.md` (skipping a small set of
exempt top-level filenames that aren't doc atoms), and assembles a
look-up-by-id and look-up-by-path index plus a list of files that couldn't be
loaded. Every check in the system runs over this graph.
"""

from __future__ import annotations

import datetime as _dt
import os
import posixpath
from dataclasses import dataclass, field
from pathlib import Path, PurePosixPath
from typing import TYPE_CHECKING

from irminsul.config import (
    IrminsulConfig,
    Layer,
    LayerName,
    docs_root_prefix,
    layer_of,
)
from irminsul.frontmatter import (
    DocFrontmatter,
    ParseFailure,
    parse_doc,
)
from irminsul.git.mtime import forget_git_history

if TYPE_CHECKING:
    from irminsul.docgraph_index import Heading, RequirementsSection, TasksSection
    from irminsul.source_map import SourceMap

# Top-level docs that aren't doc atoms — `README.md`, the glossary, contributor
# guidance, the agent manifest, the Claude Code pointer — and don't carry
# frontmatter. They're navigation, not content. `AGENTS.md` is validated by
# the `agents-manifest` check instead, which reads it directly from disk.
# `CLAUDE.md` matters when `docs_root` is the repo root, where the pointer
# `irminsul init` writes would otherwise be walked as a doc.
EXEMPT_TOPLEVEL_NAMES = frozenset(
    {"README.md", "GLOSSARY.md", "CONTRIBUTING.md", "AGENTS.md", "CLAUDE.md"}
)


@dataclass(frozen=True)
class DocNode:
    id: str
    path: Path  # repo-relative, POSIX-normalized
    frontmatter: DocFrontmatter
    body: str
    body_offset: int = 1

    def file_line(self, body_line: int) -> int:
        return body_line + self.body_offset - 1


@dataclass
class DocGraph:
    nodes: dict[str, DocNode] = field(default_factory=dict)
    by_path: dict[Path, DocNode] = field(default_factory=dict)
    parse_failures: list[ParseFailure] = field(default_factory=list)
    missing_frontmatter: list[Path] = field(default_factory=list)
    """Doc files that had no frontmatter at all (and weren't on the exemption
    list). Surfaced separately from parse failures so the FrontmatterCheck can
    word the message specifically."""
    duplicate_ids: list[tuple[str, Path, Path]] = field(default_factory=list)
    """(id, first_path, conflicting_path) tuples discovered during build."""
    config: IrminsulConfig | None = None
    repo_root: Path | None = None
    """Root of the tree this graph was walked from. Every `path` on the graph is
    relative to it."""
    state_root: Path | None = None
    """Root for run-spanning on-disk state (today: the `external-links` HTTP
    cache). Equal to `repo_root` for an ordinary run. During a `--delta` base
    pass `repo_root` is a scratch `git worktree` that is deleted on teardown,
    while `state_root` stays the user's real working tree — so both passes of
    one run read and write the same cache instead of re-fetching every URL and
    discarding the result. Anything a check must *persist* belongs here;
    anything it must *read from the tree under inspection* belongs under
    `repo_root`."""
    inbound_strong: dict[str, set[str]] = field(default_factory=dict)
    inbound_weak: dict[str, set[str]] = field(default_factory=dict)
    headings: dict[str, list[Heading]] = field(default_factory=dict)
    requirements: dict[str, RequirementsSection] = field(default_factory=dict)
    """Parsed `## Requirements` sections keyed by doc id; only docs
    that have the section appear here."""
    tasks: dict[str, TasksSection] = field(default_factory=dict)
    """Parsed `## Tasks` sections keyed by doc id; only docs that
    have the section appear here."""
    now: _dt.date | None = None
    diff_changed_paths: frozenset[str] | None = None
    """Repo-relative POSIX paths changed in the CLI's diff range, or None when
    no range resolved. Registered checks only ever receive a DocGraph, so a
    diff-aware check (`change-binding`) reads its changed set from here.
    `co-change` is unregistered and takes the same set as an argument."""
    _source_map: tuple[tuple[object, ...], SourceMap] | None = field(
        default=None, repr=False, compare=False
    )
    """`(stamp, map)` once `source_map` has been asked for. Private: a second
    interpretation of where a managed file is verified is the whole bug this
    closes, so there is one way to get one and it is the property below."""

    @property
    def source_map(self) -> SourceMap:
        """Where each managed file is verified, resolved once for this snapshot.

        Built on demand rather than in `build_graph`, because resolving it walks
        the configured source roots and every `list`, `refs` and `new` call would
        pay for an answer it never reads. Built *here* rather than per check
        because an entry is bound to whichever root the walk resolves its display
        to, and a rule that works that out for itself is a rule that can disagree
        with the others.

        Cached for the life of this graph, which is the right lifetime for two of
        its three inputs and not for the third. The configuration is this graph's
        own object and cannot drift from itself; the tree is what this graph
        walked, so the map is exactly as stale as the graph, which is the standing
        contract for every check. The record is neither — the graph never reads it
        — so it is stamped and the map is rebuilt when it moves.
        """
        from irminsul.source_map import build_source_map, record_stamp

        if self.config is None or self.repo_root is None:
            raise ValueError(
                "a DocGraph with no config or no repo root has no source map; every caller "
                "that needs one already guards on both, and answering with an empty map "
                "would be a fallback that reads as 'nothing to verify'"
            )
        stamp = record_stamp(self.repo_root, self.config)
        cached = self._source_map
        if cached is not None and cached[0] == stamp:
            return cached[1]
        from dataclasses import replace as _replace

        from irminsul.adoption import AdoptionError, AdoptionRecord, load_record, record_path

        try:
            record, unreadable = load_record(record_path(self.repo_root, self.config)), False
        except AdoptionError:
            record, unreadable = AdoptionRecord(), True
        built = build_source_map(self.repo_root, self.config, record)
        if unreadable:
            built = _replace(built, record_unreadable=True)
        self._source_map = (stamp, built)
        return built


def guidance_files(repo_root: Path, config: IrminsulConfig) -> list[tuple[str, Path]]:
    """Files that carry guidance but are not doc atoms, as (display, absolute) pairs.

    They are the configured `paths.extra_docs` and the exempt navigation files at the
    top of `docs_root`; only files that exist are returned, each once.
    """
    root = docs_root_prefix(config)
    candidates = [
        *config.paths.extra_docs,
        *(f"{root}/{name}" for name in sorted(EXEMPT_TOPLEVEL_NAMES)),
        config.checks.glossary_discipline.glossary_path,
    ]
    out: dict[str, Path] = {}
    for candidate in candidates:
        absolute = repo_root / candidate.replace("\\", "/")
        try:
            display = os.path.relpath(absolute, repo_root).replace("\\", "/")
        except ValueError:
            display = absolute.as_posix()
        display = posixpath.normpath(display)
        if display not in out and absolute.is_file():
            out[display] = absolute
    return sorted(out.items())


def is_rfc(node: DocNode, config: IrminsulConfig | None) -> bool:
    """A proposal record: a doc in the rfcs layer other than the layer's INDEX."""
    return (
        node.path.name != "INDEX.md" and layer_of(config or IrminsulConfig(), node.path) == "rfcs"
    )


def is_decision(node: DocNode, config: IrminsulConfig | None) -> bool:
    """A decision record: a doc in the decisions layer other than the layer's INDEX."""
    return (
        node.path.name != "INDEX.md"
        and layer_of(config or IrminsulConfig(), node.path) == "decisions"
    )


def layer_rules(node: DocNode, config: IrminsulConfig | None) -> tuple[LayerName, Layer] | None:
    """The layer a content doc sits in and that layer's rules; an INDEX has none."""
    config = config or IrminsulConfig()
    name = layer_of(config, node.path)
    if name is None or node.path.name == "INDEX.md":
        return None
    return name, getattr(config.layers, name)


def rfc_nodes(graph: DocGraph) -> dict[str, DocNode]:
    return {node.id: node for node in graph.nodes.values() if is_rfc(node, graph.config)}


def _to_repo_relative(absolute: Path, repo_root: Path) -> Path:
    """Repo-relative path with forward slashes, suitable for stable dict keys
    and human-readable display on Windows."""
    rel = absolute.relative_to(repo_root)
    return Path(PurePosixPath(*rel.parts))


def _walk_docs(docs_root_abs: Path) -> list[Path]:
    """Every `*.md` under the doc root, never following a directory symlink.

    `rglob` descends through one, so a junction pointing at an ancestor — which a
    Windows workspace can hold without anyone noticing — was walked until the paths
    grew too long, reporting the same docs once per level.
    """
    out: list[Path] = []
    for dirpath, dirnames, filenames in os.walk(docs_root_abs, followlinks=False):
        here = Path(dirpath)
        # `is_symlink` is False for a Windows directory junction, which is exactly the
        # link this walk exists to refuse, so both questions have to be asked.
        dirnames[:] = [
            name
            for name in dirnames
            if not (here / name).is_symlink() and not os.path.isjunction(here / name)
        ]
        out.extend(here / name for name in filenames if name.endswith(".md"))
    return sorted(out)


def build_graph(
    repo_root: Path,
    config: IrminsulConfig,
    *,
    now: _dt.date | None = None,
    diff_changed_paths: frozenset[str] | None = None,
    state_root: Path | None = None,
) -> DocGraph:
    """Walk `repo_root` and build the graph every check runs over.

    `state_root` names the root for run-spanning on-disk state and defaults to
    `repo_root`; pass it explicitly only when the walked tree is a throwaway
    checkout (the `--delta` base pass) and that state must still land in the
    caller's real repository.
    """
    # Through the prefix, not the raw field: `/` discards the left operand for an
    # absolute right, so a `docs_root` of "/etc/docs" would walk outside the
    # repository entirely — and classify against a different tree than it walked,
    # since `layer_prefix` reads the stripped prefix.
    docs_root_abs = (repo_root / docs_root_prefix(config)).resolve()
    # A graph is one invocation's view of the repository, and git history is part of it:
    # history read for an earlier graph must not answer this one, or a long-running process
    # such as the MCP server reports on the repository as it was before the last commit.
    forget_git_history()
    graph = DocGraph(
        config=config,
        repo_root=repo_root,
        state_root=state_root or repo_root,
        now=now,
        diff_changed_paths=diff_changed_paths,
    )

    if not docs_root_abs.exists():
        return graph

    for md in _walk_docs(docs_root_abs):
        rel_to_docs = md.relative_to(docs_root_abs)
        # Dot-directories hold harness and tool state (`.claude/`, `.git/`,
        # `.venv/`), never docs; the skip matters when `docs_root` is the
        # repo root, where the scaffolded skill would otherwise be walked.
        if any(part.startswith(".") for part in rel_to_docs.parts[:-1]):
            continue
        if len(rel_to_docs.parts) == 1 and rel_to_docs.name in EXEMPT_TOPLEVEL_NAMES:
            continue

        result = parse_doc(md, repo_root)
        rel_posix = _to_repo_relative(md, repo_root)

        if isinstance(result, ParseFailure):
            if result.error == "missing frontmatter":
                graph.missing_frontmatter.append(rel_posix)
            else:
                graph.parse_failures.append(
                    ParseFailure(path=rel_posix, error=result.error, data=result.data)
                )
            continue

        node = DocNode(
            id=result.frontmatter.id,
            path=rel_posix,
            frontmatter=result.frontmatter,
            body=result.body,
            body_offset=result.body_offset,
        )

        if node.id in graph.nodes:
            graph.duplicate_ids.append((node.id, graph.nodes[node.id].path, node.path))
        else:
            graph.nodes[node.id] = node

        graph.by_path[node.path] = node

    # Heading, backlink, and section indexes the checks share.
    from markdown_it import MarkdownIt

    from irminsul.docgraph_index import (
        build_headings,
        build_inbound_strong,
        build_inbound_weak,
        build_requirements,
        build_tasks,
    )

    parser = MarkdownIt("commonmark")
    graph.inbound_strong = build_inbound_strong(graph.nodes)
    graph.inbound_weak = build_inbound_weak(graph.nodes, graph.by_path, parser)
    graph.headings = build_headings(graph.nodes, parser)
    graph.requirements = build_requirements(graph.nodes)
    graph.tasks = build_tasks(graph.nodes)

    return graph
