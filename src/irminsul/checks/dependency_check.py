"""DependencyCheck — verify `depends_on` declarations match actual import relationships.

Only applies to Python source files. Uses `ast.parse` to extract imports and
resolves module paths to file paths via source_roots. Flags:
- hallucinated deps: declared in `depends_on` but no import relationship found
- undeclared deps: source imports from a doc's files but not listed in `depends_on`
"""

from __future__ import annotations

import ast
from pathlib import Path, PurePosixPath
from typing import ClassVar

from pathspec import GitIgnoreSpec

from irminsul.checks.base import Finding, Severity
from irminsul.checks.globs import walk_source_files
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

        file_to_doc: dict[Path, str] = {}
        for node in graph.nodes.values():
            if not node.frontmatter.describes:
                continue
            for pattern in node.frontmatter.describes:
                spec = GitIgnoreSpec.from_lines([pattern])
                for abs_path, display in source_files:
                    if spec.match_file(display):
                        file_to_doc[abs_path.resolve()] = node.id

        out: list[Finding] = []

        for node in graph.nodes.values():
            if not node.frontmatter.describes or not node.frontmatter.depends_on:
                continue

            actual_deps: set[str] = set()
            for pattern in node.frontmatter.describes:
                spec = GitIgnoreSpec.from_lines([pattern])
                for abs_path, display in source_files:
                    if not spec.match_file(display):
                        continue
                    if PurePosixPath(display).suffix != ".py":
                        continue
                    try:
                        text = abs_path.read_text(encoding="utf-8")
                    except OSError:
                        continue
                    for module in _extract_imports(text):
                        for candidate in _dotted_to_paths(module, source_roots, graph.repo_root):
                            doc_id = file_to_doc.get(candidate.resolve())
                            if doc_id and doc_id != node.id:
                                actual_deps.add(doc_id)

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
