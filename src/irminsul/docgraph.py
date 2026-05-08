"""Build the in-memory `DocGraph` for a codebase.

Walks `docs_root` from the config, parses every `*.md` (skipping a small set of
exempt top-level filenames that aren't doc atoms), and assembles a
look-up-by-id and look-up-by-path index plus a list of files that couldn't be
loaded. Every check in the system runs over this graph.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path, PurePosixPath

from irminsul.config import IrminsulConfig
from irminsul.frontmatter import (
    DocFrontmatter,
    ParseFailure,
    parse_doc,
)

# Top-level docs that aren't doc atoms — `README.md`, the glossary, contributor
# guidance — and don't carry frontmatter. They're navigation, not content.
EXEMPT_TOPLEVEL_NAMES = frozenset({"README.md", "GLOSSARY.md", "CONTRIBUTING.md"})


@dataclass(frozen=True)
class DocNode:
    id: str
    path: Path  # repo-relative, POSIX-normalized
    frontmatter: DocFrontmatter
    body: str


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


def _to_repo_relative(absolute: Path, repo_root: Path) -> Path:
    """Repo-relative path with forward slashes, suitable for stable dict keys
    and human-readable display on Windows."""
    rel = absolute.relative_to(repo_root)
    return Path(PurePosixPath(*rel.parts))


def build_graph(repo_root: Path, config: IrminsulConfig) -> DocGraph:
    docs_root_abs = (repo_root / config.paths.docs_root).resolve()
    graph = DocGraph(config=config, repo_root=repo_root)

    if not docs_root_abs.exists():
        return graph

    for md in sorted(docs_root_abs.rglob("*.md")):
        rel_to_docs = md.relative_to(docs_root_abs)
        if len(rel_to_docs.parts) == 1 and rel_to_docs.name in EXEMPT_TOPLEVEL_NAMES:
            continue

        result = parse_doc(md, repo_root)
        rel_posix = _to_repo_relative(md, repo_root)

        if isinstance(result, ParseFailure):
            if result.error == "missing frontmatter":
                graph.missing_frontmatter.append(rel_posix)
            else:
                graph.parse_failures.append(ParseFailure(path=rel_posix, error=result.error))
            continue

        node = DocNode(
            id=result.frontmatter.id,
            path=rel_posix,
            frontmatter=result.frontmatter,
            body=result.body,
        )

        if node.id in graph.nodes:
            graph.duplicate_ids.append((node.id, graph.nodes[node.id].path, node.path))
        else:
            graph.nodes[node.id] = node

        graph.by_path[node.path] = node

    return graph
