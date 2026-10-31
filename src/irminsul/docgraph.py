"""Build the in-memory `DocGraph` for a codebase.

Walks `docs_root` from the config, parses every `*.md` (skipping a small set of
exempt top-level filenames that aren't doc atoms), and assembles a
look-up-by-id and look-up-by-path index plus three records of what couldn't be
loaded cleanly: `parse_failures`, `missing_frontmatter` and `duplicate_ids`. Every check
in the system runs over this graph.
"""

from __future__ import annotations

import datetime as _dt
import os
import posixpath
from dataclasses import dataclass, field
from functools import cached_property
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

if TYPE_CHECKING:
    from markdown_it.token import Token

    from irminsul.adoption import AdoptionRecord
    from irminsul.checks.uniqueness import Claim
    from irminsul.docgraph_index import Heading, Link, RequirementsSection, TasksSection
    from irminsul.git.reader import GitReader
    from irminsul.source_map import SourceMap
    from irminsul.source_tree import SourceTree

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
    retired_fields: tuple[str, ...] = ()
    """Retired frontmatter keys the doc still sets; see `frontmatter.RETIRED_FIELDS`."""

    def file_line(self, body_line: int) -> int:
        return body_line + self.body_offset - 1

    @cached_property
    def tokens(self) -> list[Token]:
        """The body's markdown tokens, parsed once for every reader of this node.

        Shared, so a reader must not change them."""
        from irminsul.docgraph_index import parse_markdown

        return parse_markdown(self.body)

    @cached_property
    def links(self) -> list[Link]:
        """The body's links, read once from `tokens`. Shared, so a reader must not change them."""
        from irminsul.docgraph_index import links_of

        return links_of(self.tokens)


@dataclass(frozen=True)
class GuidanceFile:
    """A file that carries guidance but is not a doc atom, read once for the graph."""

    display: str
    """Spelled relative to the repo root, so `../code/README.md` for a sibling repository's."""
    absolute: Path
    text: str | None
    """None when the file would not open or decode."""
    unreadable: str | None
    """Why `text` is None, or None when it is not, or the file went between listing and reading."""
    root: str | None
    """The root of the repository the file lives in, spelled like `display`: what a link in
    it that climbs with `..` is measured against. A link that starts with `/` is not
    judged. None when that repository is not a git checkout, which sets no limit."""

    @cached_property
    def tokens(self) -> list[Token]:
        from irminsul.docgraph_index import parse_markdown

        return parse_markdown(self.text or "")

    @cached_property
    def links(self) -> list[Link]:
        from irminsul.docgraph_index import links_of

        return links_of(self.tokens)

    @cached_property
    def headings(self) -> list[Heading]:
        from irminsul.docgraph_index import headings_of

        return headings_of(self.tokens)


@dataclass(frozen=True)
class ChangeRange:
    """The diff range a run judges; `checks.change_range` resolves it from git."""

    base: str
    head: str | None
    """The commit the range ends at, or None for the working tree, which is what a run
    judges unless it is given `--committed-only`."""
    changed: frozenset[str]
    """Repo-relative POSIX paths that differ between `merge_base` and the end of the range."""
    merge_base: str
    """The commit every pass reads the before side at, resolved once so that the base
    branch moving on is never part of the change."""
    uncommitted: frozenset[str] = frozenset()
    """The changed paths the commits do not hold; empty when the range ends at a commit."""
    source_changed: frozenset[str] = frozenset()
    """What `--source-diff` says a sibling source repository changed, in display
    spellings. It reaches touch-to-own over recorded debt and nothing else."""

    @property
    def commit(self) -> str:
        """The commit to read commit-bound facts at: trailers, and the commits after one."""
        return self.head or "HEAD"


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
    """Root for run-spanning on-disk state (such as the `external-links` HTTP
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
    change: ChangeRange | None = None
    """The diff range this run judges, or None for a run that judges the tree alone.
    Every pass that judges the change reads it from here, so they agree about what
    changed."""
    committed_only: bool = False
    """Whether the run was given `--committed-only`: work not yet committed is left out of
    what it judges. A pass reads the committed side of a change, and history is read from
    commits alone, where by default a path with uncommitted changes reads as changed after
    every commit. One switch, so no two readers can disagree about what "committed"
    means."""
    _source_map: SourceMap | None = field(default=None, init=False, repr=False, compare=False)
    """Set once `source_map` has been asked for. Private: a second interpretation of
    where a managed file is verified would disagree with the first, so there is one way
    to get one and it is the property below."""
    _source: SourceTree | None = field(default=None, init=False, repr=False, compare=False)
    _claims: dict[str, list[Claim]] | None = field(
        default=None, init=False, repr=False, compare=False
    )
    _git: GitReader | None = field(default=None, init=False, repr=False, compare=False)
    _guidance_files: list[GuidanceFile] | None = field(
        default=None, init=False, repr=False, compare=False
    )
    _adoption: tuple[AdoptionRecord | None, str | None] | None = field(
        default=None, init=False, repr=False, compare=False
    )

    def doc_at(self, path: str) -> DocNode | None:
        """The doc a repo-relative path written in frontmatter names, such as `resolved_by`."""
        return self.by_path.get(declared_path(path))

    @property
    def guidance_files(self) -> list[GuidanceFile]:
        """The guidance files outside the doc graph, each read once for this graph.

        The README and the agent guides are checked for links, ignore comments, code names,
        retired wording and review sentences, and each of those reads the same text. Shared,
        so a reader must not change it.
        """
        if self.config is None or self.repo_root is None:
            return []
        if self._guidance_files is None:
            self._guidance_files = read_guidance(self.repo_root, self.config)
        return self._guidance_files

    @property
    def source(self) -> SourceTree:
        """This graph's snapshot of the configured source, created on first use.

        Every check in a run reads the same one, so each part of it is derived once per
        invocation rather than once per check. Not an init field, so
        `dataclasses.replace` cannot hand one graph's snapshot to another.
        """
        if self.config is None or self.repo_root is None:
            raise ValueError("a DocGraph with no config or no repo root has no source tree")
        if self._source is None:
            from irminsul.source_tree import SourceTree

            self._source = SourceTree(self.repo_root, self.config)
        return self._source

    @property
    def git(self) -> GitReader:
        """This graph's questions to git, each asked once for the life of the graph.

        A graph is one invocation's view of the repository, and git history is part of it:
        history read for an earlier graph must not answer this one, or a long-running
        process such as the MCP server reports on the repository as it was before the last
        commit. Owning the reader is what bounds it — and a second graph in one invocation,
        the base side of `--delta`, asks for itself without discarding what this one read.
        """
        if self._git is None:
            from irminsul.git.mtime import pending_time
            from irminsul.git.reader import GitReader

            self._git = GitReader(pending=None if self.committed_only else pending_time(self.now))
        return self._git

    @property
    def claims(self) -> dict[str, list[Claim]]:
        """Each walked source file's `describes` claims, resolved once for this graph.

        `uniqueness`, both import checks, `diff-integrity` and adoption all ask who owns a
        file, and reading one table is what keeps them from answering differently. Shared,
        so a reader must not change it.
        """
        if self._claims is None:
            from irminsul.checks.uniqueness import resolve_claims

            self._claims = resolve_claims(self, [display for _, display in self.source.files])
        return self._claims

    def _read_adoption(self) -> tuple[AdoptionRecord | None, str | None]:
        if self._adoption is None:
            from irminsul.adoption import AdoptionError, load_record, record_path

            record: AdoptionRecord | None = None
            error: str | None = None
            if self.config is not None and self.repo_root is not None:
                path = record_path(self.repo_root, self.config)
                if path.is_file():
                    try:
                        record = load_record(path)
                    except AdoptionError as exc:
                        error = str(exc)
            self._adoption = (record, error)
        return self._adoption

    @property
    def adoption_record(self) -> AdoptionRecord | None:
        """The adoption record, parsed once for this graph.

        `None` when the repository keeps none, which is the ordinary case, and when the one it
        keeps cannot be read; `adoption_error` says which. The two are different answers
        (no record keeps the progressive ownership rules, an unreadable one is a finding), so
        a reader that needs to tell them apart asks both. Shared, so a reader must not
        change it.
        """
        return self._read_adoption()[0]

    @property
    def adoption_error(self) -> str | None:
        """Why the adoption record could not be read, or `None` when it was, or is absent."""
        return self._read_adoption()[1]

    @property
    def source_map(self) -> SourceMap:
        """Where each managed file is verified, resolved once for this snapshot.

        Built on demand rather than in `build_graph`, because resolving it walks
        the configured source roots and every `list`, `refs` and `new` call would
        pay for an answer it never reads. Built *here* rather than per check
        because an entry is bound to whichever root the walk resolves its display
        to, and a rule that works that out for itself is a rule that can disagree
        with the others.

        Cached for the life of this graph: the configuration is this graph's own
        object, and the tree and the record are read as they stood when the map was
        first asked for, the same snapshot contract every check holds to.
        """
        from irminsul.source_map import build_source_map

        if self.config is None or self.repo_root is None:
            raise ValueError(
                "a DocGraph with no config or no repo root has no source map; every caller "
                "that needs one already guards on both, and answering with an empty map "
                "would be a fallback that reads as 'nothing to verify'"
            )
        if self._source_map is not None:
            return self._source_map
        from dataclasses import replace as _replace

        from irminsul.adoption import AdoptionRecord

        record = self.adoption_record
        built = build_source_map(self.source, record if record is not None else AdoptionRecord())
        if self.adoption_error is not None:
            built = _replace(built, record_unreadable=True)
        self._source_map = built
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


def read_guidance(repo_root: Path, config: IrminsulConfig) -> list[GuidanceFile]:
    """Every guidance file, read; `DocGraph.guidance_files` is the cached way to ask."""
    out: list[GuidanceFile] = []
    for display, absolute in guidance_files(repo_root, config):
        text: str | None
        unreadable: str | None = None
        try:
            text = absolute.read_text(encoding="utf-8")
        except FileNotFoundError:
            text = None
        except (OSError, UnicodeDecodeError) as exc:
            text, unreadable = None, f"{type(exc).__name__}: {exc}"
        out.append(
            GuidanceFile(
                display, absolute, text, unreadable, _own_root(repo_root, display, absolute)
            )
        )
    return out


def _own_root(repo_root: Path, display: str, absolute: Path) -> str | None:
    if not (display.startswith("../") or Path(display).is_absolute()):
        return ""
    from irminsul.git.mtime import git_root_for

    git_root = git_root_for(absolute)
    if git_root is None:
        return None
    try:
        return posixpath.normpath(os.path.relpath(git_root, repo_root.resolve()).replace("\\", "/"))
    except ValueError:
        return None


def _spelled_from_root(repo_root: Path | None, target: str) -> str:
    """`target` as a path spelled relative to the repo root, the way displays are."""
    raw = Path(target)
    if repo_root is not None and raw.is_absolute():
        try:
            rel = os.path.relpath(raw.resolve(), repo_root.resolve())
        except ValueError:
            return target
        return posixpath.normpath(rel.replace("\\", "/"))
    return posixpath.normpath(target.replace("\\", "/"))


def declared_path(path: str) -> Path:
    """The graph key of a repo-relative path written in frontmatter.

    `\\` is read as a separator on every platform, so a path written on Windows names the
    same doc in a Linux run as it does where it was written.
    """
    return Path(PurePosixPath(path.replace("\\", "/")))


def resolve_doc_target(graph: DocGraph, target: str) -> str | None:
    """The repo-relative POSIX path of the doc `target` names by id or by path, or None.

    The path may be relative to the repo root or absolute. A guidance file such as the root
    `AGENTS.md` has no id but answers to its path. None lets a caller refuse a doc that
    does not exist: an option that matches nothing and prints an empty result reads as
    "nothing to do here", which is the wrong answer to a typo or to an id where a path is
    expected.
    """
    node = graph.nodes.get(target)
    if node is not None:
        return node.path.as_posix()
    wanted = _spelled_from_root(graph.repo_root, target)
    if Path(wanted) in graph.by_path or any(g.display == wanted for g in graph.guidance_files):
        return wanted
    return None


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
    Windows workspace can hold without anyone noticing — would be walked until the paths
    grow too long, reporting the same docs once per level.
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
    change: ChangeRange | None = None,
    committed_only: bool = False,
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
    graph = DocGraph(
        config=config,
        repo_root=repo_root,
        state_root=state_root or repo_root,
        now=now,
        change=change,
        committed_only=committed_only,
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
            retired_fields=result.retired_fields,
        )

        if node.id in graph.nodes:
            graph.duplicate_ids.append((node.id, graph.nodes[node.id].path, node.path))
        else:
            graph.nodes[node.id] = node

        graph.by_path[node.path] = node

    # Heading, backlink, and section indexes the checks share.
    from irminsul.docgraph_index import (
        build_headings,
        build_inbound_strong,
        build_inbound_weak,
        build_requirements,
        build_tasks,
    )

    graph.inbound_strong = build_inbound_strong(graph.nodes)
    graph.inbound_weak = build_inbound_weak(graph.nodes, graph.by_path)
    graph.headings = build_headings(graph.nodes)
    graph.requirements = build_requirements(graph.nodes)
    graph.tasks = build_tasks(graph.nodes)

    return graph
