"""Derived change footprint: changed paths resolved to owning components.

The footprint is recomputed from a diff and the graph on every call — it is
never stored on the RFC. Ownership resolution reuses `resolve_claims`, the same
primitive behind `uniqueness` and `context --changed`, so "which component owns
this changed file" has exactly one answer everywhere.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path, PurePosixPath

from pathspec import GitIgnoreSpec

from irminsul.checks.globs import is_configured_source_path, walk_configured_source_files
from irminsul.checks.uniqueness import resolve_claims
from irminsul.config import IrminsulConfig, docs_root_prefix
from irminsul.docgraph import DocGraph, DocNode


@dataclass(frozen=True)
class Footprint:
    """Where a set of changed paths landed, in component terms."""

    changed_paths: tuple[str, ...]
    touched: dict[str, tuple[str, ...]] = field(default_factory=dict)
    """Component doc id -> changed source files it owns (most-specific claim)."""
    unowned_source: tuple[str, ...] = ()
    """Changed source files with no doc claim (delegated to coverage/uniqueness)."""
    changed_docs: tuple[str, ...] = ()
    changed_tests: dict[str, tuple[str, ...]] = field(default_factory=dict)
    """Component doc id -> changed files matched by that doc's `tests:` entries."""


def most_specific_claims(
    claims: list[tuple[DocNode, str, tuple[int, int, int]]],
) -> list[DocNode]:
    """The doc(s) owning a file under the most-specific-claim rule (`uniqueness`).

    A broader parent claim is shadowed by a narrower child claim; only a genuine
    tie at the top score yields more than one owner.
    """
    if not claims:
        return []
    top_score = max(score for _, _, score in claims)
    return [node for node, _, score in claims if score == top_score]


def touched_components(
    graph: DocGraph,
    config: IrminsulConfig,
    changed_paths: frozenset[str],
) -> Footprint:
    """Resolve `changed_paths` (repo-relative POSIX) to owning components.

    A deleted file is not on disk, so it cannot come from the source walk — it
    is resolved from its path alone. Removing a file is a change to the
    component that owned it, and an undeclared removal must surface as loudly as
    an undeclared edit.
    """
    assert graph.repo_root is not None
    repo_root = graph.repo_root
    source_files = walk_configured_source_files(repo_root, config).files
    on_disk = {display for _, display in source_files}

    changed_source: list[tuple[Path, str]] = [
        (abs_path, display) for abs_path, display in source_files if display in changed_paths
    ]
    changed_source.extend(
        (repo_root / path, path)
        for path in sorted(changed_paths)
        if path not in on_disk and is_configured_source_path(repo_root, config, path)
    )
    claims_by_file = resolve_claims(graph, changed_source)

    touched: dict[str, list[str]] = {}
    unowned: list[str] = []
    for _, display in changed_source:
        owners = most_specific_claims(claims_by_file.get(display, []))
        if not owners:
            unowned.append(display)
            continue
        for node in owners:
            touched.setdefault(node.id, []).append(display)

    docs_root = docs_root_prefix(config)
    changed_docs = sorted(
        path for path in changed_paths if PurePosixPath(path).is_relative_to(docs_root)
    )

    changed_tests: dict[str, tuple[str, ...]] = {}
    for node in graph.nodes.values():
        if not node.frontmatter.tests:
            continue
        spec = GitIgnoreSpec.from_lines(node.frontmatter.tests)
        hits = sorted(path for path in changed_paths if spec.match_file(path))
        if hits:
            changed_tests[node.id] = tuple(hits)

    return Footprint(
        changed_paths=tuple(sorted(changed_paths)),
        touched={doc_id: tuple(sorted(files)) for doc_id, files in sorted(touched.items())},
        unowned_source=tuple(sorted(unowned)),
        changed_docs=tuple(changed_docs),
        changed_tests=changed_tests,
    )
