"""DependencyCheck — verify `depends_on` declarations match actual import relationships.

Only applies to `IMPORT_LANGUAGE`'s source files. Uses `ast.parse` to extract imports and
resolves module paths to file paths via source_roots. Flags hallucinated deps:
`depends_on` declared but with no import relationship found. The reverse direction
(imports not declared) is intentionally not flagged: `depends_on` is
curated intent, not a complete projection of the import graph. A doc that mixes Python
with another language is read through its Python alone, so a dependency only its other
code backs is still reported.
"""

from __future__ import annotations

import ast
import os
from dataclasses import dataclass, field
from pathlib import Path, PurePosixPath
from typing import ClassVar

from irminsul.checks.base import Finding, FindingClass, Severity
from irminsul.docgraph import DocGraph
from irminsul.inventory.base import PythonModule
from irminsul.languages import PYTHON_PROFILE

IMPORT_LANGUAGE = PYTHON_PROFILE
"""The one language whose imports are read. A file of another language is a relationship
the check cannot see, so a doc that owns none of this language's files is not judged."""


def imported_paths(
    module: PythonModule, importer: Path, source_roots: list[str], repo_root: Path
) -> list[Path]:
    """Candidate files the imports in `module` may load, at any depth in the tree.

    `from pkg import b` may load the submodule `pkg.b` as well as a name defined in
    `pkg`, so both are candidates, and a relative import resolves against `importer`'s
    own package. Reading only `pkg`, or only absolute imports, would miss a dependency the
    code plainly has.
    """
    roots = [repo_root / root for root in source_roots]
    out: list[Path] = []
    for node in module.nodes:
        if isinstance(node, ast.Import):
            for alias in node.names:
                for base in roots:
                    out.extend(_module_files(base, alias.name.split(".")))
        elif isinstance(node, ast.ImportFrom):
            parts = node.module.split(".") if node.module else []
            if node.level:
                package = importer.parent
                for _ in range(node.level - 1):
                    package = package.parent
                bases = [package]
            elif parts:
                bases = roots
            else:
                continue
            names = [alias.name for alias in node.names if alias.name != "*"]
            for base in bases:
                out.extend(_module_files(base, parts))
                for name in names:
                    out.extend(_module_files(base, [*parts, name]))
    return out


def _module_files(base: Path, parts: list[str]) -> list[Path]:
    """The two files that can hold the module `parts` names under `base`."""
    if not parts:
        return [base / "__init__.py"]
    target = base.joinpath(*parts)
    return [target.with_suffix(".py"), target / "__init__.py"]


@dataclass(frozen=True)
class SourceOwnership:
    """Which doc owns each configured source file, and each doc's Python files."""

    file_to_doc: dict[Path, str]
    """Resolved absolute path → owning doc id."""
    doc_py_files: dict[str, list[Path]]
    """Doc id → the Python files it owns, so a second pass need not re-match globs."""
    real_paths: dict[str, Path | None] = field(default_factory=dict, repr=False, compare=False)
    """As-written path → resolved path, `None` for a path that names nothing.

    Resolving a path is a filesystem call that costs about a millisecond on Windows, and
    import candidates repeat across files, so each spelling is resolved at most once."""

    def owner_of(self, candidate: Path) -> str | None:
        """The doc owning the file `candidate` names, or None when it names no owned file.

        A path that does not exist resolves to a path that does not exist, and every key of
        `file_to_doc` is the resolved path of a file that does, so it is skipped without
        resolving. Keyed by the spelling rather than by the `Path`, which compares
        case-insensitively on Windows even where the filesystem does not."""
        key = os.fspath(candidate)
        if key not in self.real_paths:
            self.real_paths[key] = candidate.resolve() if os.path.lexists(candidate) else None
        real = self.real_paths[key]
        return None if real is None else self.file_to_doc.get(real)


def resolve_ownership(graph: DocGraph) -> SourceOwnership:
    """Map every configured source file to the doc whose `describes` glob matches best.

    When several docs claim one file the most specific pattern wins, read from the graph's
    one claims table that `uniqueness` judges; a true tie is an error there, and here it is
    broken by doc id so two runs agree. Both import checks route through this, so "who
    owns this file?" has one answer for both.
    """
    if graph.config is None or graph.repo_root is None:
        return SourceOwnership(file_to_doc={}, doc_py_files={})

    claims_by_file = graph.claims
    by_real: dict[Path, list[tuple[str, tuple[int, int, int]]]] = {}
    doc_py_files: dict[str, list[Path]] = {
        node.id: [] for node in graph.nodes.values() if node.frontmatter.describes
    }
    real_paths: dict[str, Path | None] = {}

    for abs_path, display in graph.source.files:
        claims = claims_by_file.get(display)
        if not claims:
            continue
        real = real_paths.get(os.fspath(abs_path))
        if real is None:
            real = real_paths[os.fspath(abs_path)] = abs_path.resolve()
        by_real.setdefault(real, []).extend((node.id, score) for node, _, score in claims)
        if PurePosixPath(display).suffix in IMPORT_LANGUAGE.suffixes:
            for doc_id in dict.fromkeys(node.id for node, _, _ in claims):
                doc_py_files[doc_id].append(abs_path)

    file_to_doc: dict[Path, str] = {}
    for file_path, file_claims in by_real.items():
        top_score = max(c[1] for c in file_claims)
        file_to_doc[file_path] = min(c[0] for c in file_claims if c[1] == top_score)
    return SourceOwnership(
        file_to_doc=file_to_doc, doc_py_files=doc_py_files, real_paths=real_paths
    )


CODE_HALLUCINATED_DEPENDENCY = "import-deps/hallucinated-dependency"


class DependencyCheck:
    name: ClassVar[str] = "import-deps"
    default_severity: ClassVar[Severity] = Severity.warning
    explanations: ClassVar[dict[str, str]] = {
        CODE_HALLUCINATED_DEPENDENCY: (
            "A `depends_on` entry is declared but no import relationship backs it in "
            f"code. Only {IMPORT_LANGUAGE.name} imports are read, so a doc or dependency "
            f"that owns no {IMPORT_LANGUAGE.name} file is not judged. Remove the stale "
            "declaration, or verify the doc claiming the dependent module actually covers "
            "the right files."
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
        doc_py_files = ownership.doc_py_files

        out: list[Finding] = []
        for node in graph.nodes.values():
            # Only Python imports are read, so a doc that owns no Python file, or a
            # dependency that owns none, is a relationship this check cannot see; judging
            # it would report every true `depends_on` of such a doc as hallucinated.
            py_files = doc_py_files.get(node.id, [])
            if not py_files:
                continue

            actual_deps: set[str] = set()
            for abs_path in py_files:
                module = graph.source.module(abs_path)
                if module is None:
                    continue
                for candidate in imported_paths(module, abs_path, source_roots, graph.repo_root):
                    dep_id = ownership.owner_of(candidate)
                    if dep_id and dep_id != node.id:
                        actual_deps.add(dep_id)

            declared_deps = {dep for dep in node.frontmatter.depends_on if doc_py_files.get(dep)}

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
