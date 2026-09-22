"""Source files whose owning doc a change moved to another doc.

A file's owner is the doc whose `describes` claims it most specifically. When a change
narrows one doc's claim and adds another's, the file keeps a single owner, so nothing
reports a duplicate claim, yet the old owner's prose about the file can stay behind.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from pathspec import GitIgnoreSpec

from irminsul.checks.globs import walk_configured_source_files
from irminsul.checks.uniqueness import specificity
from irminsul.config import docs_root_prefix
from irminsul.docgraph import DocGraph
from irminsul.frontmatter_edit import split_frontmatter
from irminsul.git.changes import GitChangesError, file_at_ref, files_at_ref


@dataclass(frozen=True)
class OwnerMove:
    file: str
    before: tuple[str, ...]
    after: tuple[str, ...]


def owners(describes: dict[str, list[str]], displays: list[str]) -> dict[str, tuple[str, ...]]:
    """Each claimed display path's most specific claimants, as sorted doc paths."""
    claims: dict[str, list[tuple[tuple[int, int, int], str]]] = {}
    for doc, patterns in describes.items():
        for pattern in patterns:
            score = specificity(pattern)
            for display in GitIgnoreSpec.from_lines([pattern]).match_files(displays):
                claims.setdefault(display, []).append((score, doc))
    out: dict[str, tuple[str, ...]] = {}
    for display, found in claims.items():
        top = max(score for score, _ in found)
        out[display] = tuple(sorted({doc for score, doc in found if score == top}))
    return out


def owner_moves(
    graph: DocGraph,
    changed: set[str] | frozenset[str],
    base: str,
    read: Callable[[str, str], str | None] | None = None,
) -> list[OwnerMove]:
    """Files owned by some doc at `base` and by a different doc now.

    Docs are matched by id, so a doc that moved to another path keeps its files.

    `read` lets a caller that already fetched these blobs at `base` share its memo,
    rather than paying a second `git show` for each doc.
    """
    if graph.config is None or graph.repo_root is None:
        return []
    repo_root = graph.repo_root
    prefix = f"{docs_root_prefix(graph.config)}/"
    after = {node.id: list(node.frontmatter.describes) for node in graph.nodes.values()}
    shown = {node.id: node.path.as_posix() for node in graph.nodes.values()}
    before = dict(after)
    at_base: dict[str, list[str]] = {}
    at_head: set[str] = set()
    try:
        gone = {
            path
            for path in files_at_ref(repo_root, base, prefix.rstrip("/"))
            if Path(path) not in graph.by_path
        }
    except GitChangesError:
        gone = set()
    for path in sorted({*changed, *gone}):
        if not path.startswith(prefix) or not path.endswith(".md"):
            continue
        try:
            old = read(base, path) if read is not None else file_at_ref(repo_root, base, path)
        except GitChangesError:
            return []
        node = graph.by_path.get(Path(path))
        if node is not None:
            at_head.add(node.id)
        if old is not None:
            doc_id, describes = _frontmatter(old, Path(path).stem)
            at_base[doc_id] = describes
            shown.setdefault(doc_id, path)
    for doc_id in at_head - set(at_base):
        before.pop(doc_id, None)
    before.update(at_base)
    if before == after:
        return []
    displays = [
        display for _, display in walk_configured_source_files(repo_root, graph.config).files
    ]
    was = owners(before, displays)
    now = owners(after, displays)
    return [
        OwnerMove(
            display,
            tuple(sorted(shown[doc] for doc in was[display])),
            tuple(sorted(shown[doc] for doc in now[display])),
        )
        for display in sorted(set(was) & set(now))
        if was[display] != now[display]
    ]


def _frontmatter(text: str, fallback_id: str) -> tuple[str, list[str]]:
    """A doc's id and `describes` as written in `text`."""
    from ruamel.yaml import YAML

    try:
        raw, _ = split_frontmatter(text)
        data = YAML(typ="safe").load(raw)
    except Exception:
        return fallback_id, []
    if not isinstance(data, dict):
        return fallback_id, []
    value = data.get("describes")
    describes = [str(item) for item in value] if isinstance(value, list) else []
    return str(data.get("id") or fallback_id), describes


def file_names(display: str) -> list[str]:
    """How prose names a source file: its path, and its file name."""
    return [display, Path(display).name]
