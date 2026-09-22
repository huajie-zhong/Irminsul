"""DependencyCheck — verify `depends_on` declarations match actual import relationships.

Only applies to Python source files. Uses `ast.parse` to extract imports and
resolves module paths to file paths via source_roots. Flags hallucinated deps:
`depends_on` declared but with no import relationship found. The reverse direction
(imports not declared) is intentionally not flagged: `depends_on` is
curated intent, not a complete projection of the import graph.
"""

from __future__ import annotations

import ast
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import ClassVar

from pathspec import GitIgnoreSpec

from irminsul.checks.base import Finding, FindingClass, Severity
from irminsul.checks.globs import walk_configured_source_files
from irminsul.checks.uniqueness import specificity
from irminsul.docgraph import DocGraph


def extract_imports(source: str) -> list[str]:
    """Return dotted module names from absolute import/from-import statements."""
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return []
    modules: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                modules.append(alias.name)
        elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
            modules.append(node.module)
    return modules


def dotted_to_paths(module: str, source_roots: list[str], repo_root: Path) -> list[Path]:
    """Convert 'a.b.c' to candidate file paths under each source root."""
    parts = module.split(".")
    candidates: list[Path] = []
    for root in source_roots:
        base = repo_root / root
        p = base.joinpath(*parts)
        candidates.append(p.with_suffix(".py"))
        candidates.append(p / "__init__.py")
    return candidates


@dataclass(frozen=True)
class SourceOwnership:
    """Which doc owns each configured source file, and each doc's Python files."""

    file_to_doc: dict[Path, str]
    """Resolved absolute path → owning doc id."""
    doc_py_files: dict[str, list[Path]]
    """Doc id → the Python files it owns, so a second pass need not re-match globs."""


def resolve_ownership(graph: DocGraph) -> SourceOwnership:
    """Map every configured source file to the doc whose `describes` glob matches best.

    When several docs claim one file the most specific pattern wins, scored the same way
    `uniqueness` scores it; a true tie is an error there, and here it is broken by doc id
    so two runs agree. Both import checks route through this, so "who owns this file?"
    has one answer for both.
    """
    if graph.config is None or graph.repo_root is None:
        return SourceOwnership(file_to_doc={}, doc_py_files={})

    source_files = walk_configured_source_files(graph.repo_root, graph.config).files
    claims: dict[Path, list[tuple[str, tuple[int, int, int]]]] = defaultdict(list)
    doc_py_files: dict[str, list[Path]] = {}

    for node in graph.nodes.values():
        if not node.frontmatter.describes:
            continue
        pattern_specs = sorted(
            [
                (p, specificity(p), GitIgnoreSpec.from_lines([p]))
                for p in node.frontmatter.describes
            ],
            key=lambda x: x[1],
            reverse=True,
        )
        node_py: list[Path] = []
        for abs_path, display in source_files:
            best_score: tuple[int, int, int] | None = None
            for _pat, score, pspec in pattern_specs:
                if pspec.match_file(display):
                    best_score = score
                    break  # sorted descending; first match is highest score
            if best_score is None:
                continue
            claims[abs_path.resolve()].append((node.id, best_score))
            if PurePosixPath(display).suffix == ".py":
                node_py.append(abs_path)
        doc_py_files[node.id] = node_py

    file_to_doc: dict[Path, str] = {}
    for file_path, file_claims in claims.items():
        top_score = max(c[1] for c in file_claims)
        winners = sorted(c[0] for c in file_claims if c[1] == top_score)
        file_to_doc[file_path] = winners[0]
    return SourceOwnership(file_to_doc=file_to_doc, doc_py_files=doc_py_files)


CODE_HALLUCINATED_DEPENDENCY = "import-deps/hallucinated-dependency"


class DependencyCheck:
    name: ClassVar[str] = "import-deps"
    default_severity: ClassVar[Severity] = Severity.warning
    explanations: ClassVar[dict[str, str]] = {
        CODE_HALLUCINATED_DEPENDENCY: (
            "A `depends_on` entry is declared but no import relationship backs it in "
            "code. Remove the stale declaration, or verify the doc claiming the "
            "dependent module actually covers the right files."
        ),
    }
    classes: ClassVar[dict[str, FindingClass]] = {
        CODE_HALLUCINATED_DEPENDENCY: FindingClass.hint,
    }

    def run(self, graph: DocGraph) -> list[Finding]:
        if graph.config is None or graph.repo_root is None:
            return []

        source_roots = graph.config.paths.source_roots
        ownership = resolve_ownership(graph)
        file_to_doc = ownership.file_to_doc
        doc_py_files = ownership.doc_py_files

        out: list[Finding] = []

        # Pass 2: reuse pre-computed doc_py_files — no re-matching needed.
        for node in graph.nodes.values():
            if not node.frontmatter.describes:
                continue

            actual_deps: set[str] = set()
            for abs_path in doc_py_files.get(node.id, []):
                try:
                    text = abs_path.read_text(encoding="utf-8")
                except OSError:
                    continue
                for module in extract_imports(text):
                    for candidate in dotted_to_paths(module, source_roots, graph.repo_root):
                        dep_id = file_to_doc.get(candidate.resolve())
                        if dep_id and dep_id != node.id:
                            actual_deps.add(dep_id)

            declared_deps = set(node.frontmatter.depends_on)

            # Intent-only: flag a declared dependency that has no actual
            # import (a hallucinated/stale declaration), but never the reverse —
            # forcing `depends_on` to mirror every import is the materialization
            # pressure the "derive, don't materialize" principle rejects. depends_on
            # is curated intent, not a complete projection of the import graph.
            for dep_id in sorted(declared_deps - actual_deps):
                out.append(
                    Finding(
                        check=self.name,
                        code=CODE_HALLUCINATED_DEPENDENCY,
                        severity=Severity.warning,
                        message=f"depends_on '{dep_id}' declared but no import relationship found",
                        path=node.path,
                        doc_id=node.id,
                    )
                )

        return out
