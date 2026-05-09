"""DependencyCheck — verify `depends_on` declarations match actual import relationships.

Only applies to Python source files. Uses `ast.parse` to extract imports and
resolves module paths to file paths via source_roots. Flags:
- hallucinated deps: declared in `depends_on` but no import relationship found
- undeclared deps: source imports from a doc's files but not listed in `depends_on`
"""

from __future__ import annotations

import ast
from collections import defaultdict
from pathlib import Path, PurePosixPath
from typing import ClassVar

from pathspec import GitIgnoreSpec

from irminsul.checks.base import Finding, Severity
from irminsul.checks.globs import walk_source_files
from irminsul.checks.uniqueness import specificity
from irminsul.docgraph import DocGraph


def _extract_imports(source: str) -> list[str]:
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


def _dotted_to_paths(module: str, source_roots: list[str], repo_root: Path) -> list[Path]:
    """Convert 'a.b.c' to candidate file paths under each source root."""
    parts = module.split(".")
    candidates: list[Path] = []
    for root in source_roots:
        base = repo_root / root
        p = base.joinpath(*parts)
        candidates.append(p.with_suffix(".py"))
        candidates.append(p / "__init__.py")
    return candidates


class DependencyCheck:
    name: ClassVar[str] = "import-deps"
    default_severity: ClassVar[Severity] = Severity.warning

    def run(self, graph: DocGraph) -> list[Finding]:
        if graph.config is None or graph.repo_root is None:
            return []

        source_roots = graph.config.paths.source_roots
        source_files, _ = walk_source_files(graph.repo_root, source_roots)

        # Pass 1: build file→doc ownership (specificity-aware) and cache each
        # doc's Python files to avoid re-matching in pass 2.
        #
        # claims maps abs_path → list of (node_id, best_pattern_specificity).
        # When multiple docs claim the same file, the most-specific pattern wins
        # (same rule as UniquenessCheck). Ties are broken by node_id for
        # determinism; UniquenessCheck already errors on true ties.
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
                for module in _extract_imports(text):
                    for candidate in _dotted_to_paths(module, source_roots, graph.repo_root):
                        dep_id = file_to_doc.get(candidate.resolve())
                        if dep_id and dep_id != node.id:
                            actual_deps.add(dep_id)

            declared_deps = set(node.frontmatter.depends_on)

            for dep_id in sorted(declared_deps - actual_deps):
                out.append(
                    Finding(
                        check=self.name,
                        severity=Severity.warning,
                        message=f"depends_on '{dep_id}' declared but no import relationship found",
                        path=node.path,
                        doc_id=node.id,
                    )
                )

            for dep_id in sorted(actual_deps - declared_deps):
                out.append(
                    Finding(
                        check=self.name,
                        severity=Severity.warning,
                        message=f"source imports from '{dep_id}' but depends_on is not declared",
                        path=node.path,
                        doc_id=node.id,
                    )
                )

        return out
