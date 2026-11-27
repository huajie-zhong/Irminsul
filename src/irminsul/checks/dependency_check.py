"""DependencyCheck — verify `depends_on` declarations match actual import relationships.

A file's imports are read by its language's reader (`irminsul.languages`), which also says
which repository files each may load, so only a file of a language that has a reader backs
a dependency. Flags hallucinated deps: `depends_on` declared but with no import
relationship found. The reverse direction (imports not declared) is intentionally not
flagged: `depends_on` is curated intent, not a complete projection of the import graph.

A missing import says two docs are unrelated only where an import would have shown the
relation: the two own code of a language in common, and every import of the depending
doc's files of each such language is placed, which a reading says of its file. A file whose
imports are only partly placed, because a path alias or another package may stand between
two files or because it does not parse, backs a dependency it finds and denies none. A doc
that also owns code no reader reads is judged through the rest alone, so a dependency only
that code backs is still reported.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import ClassVar

from irminsul.checks.base import Answer, Finding, FindingClass, Severity
from irminsul.docgraph import DocGraph
from irminsul.languages import language_read, reader_for
from irminsul.languages.reader import imported_files


@dataclass(frozen=True)
class SourceOwnership:
    """Which doc owns each configured source file, and each doc's files a reader reads."""

    file_to_doc: dict[Path, str]
    """Resolved absolute path → owning doc id."""
    doc_code_files: dict[str, list[Path]]
    """Doc id → the files it owns whose language has a reader, so a second pass need not
    re-match globs. A file of any other language is a relationship the import checks cannot
    see, so a doc that owns none of these is not judged."""
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
        return SourceOwnership(file_to_doc={}, doc_code_files={})

    claims_by_file = graph.claims
    by_real: dict[Path, list[tuple[str, tuple[int, int, int]]]] = {}
    doc_code_files: dict[str, list[Path]] = {
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
        if reader_for(display) is not None:
            for doc_id in dict.fromkeys(node.id for node, _, _ in claims):
                doc_code_files[doc_id].append(abs_path)

    file_to_doc: dict[Path, str] = {}
    for file_path, file_claims in by_real.items():
        top_score = max(c[1] for c in file_claims)
        file_to_doc[file_path] = min(c[0] for c in file_claims if c[1] == top_score)
    return SourceOwnership(
        file_to_doc=file_to_doc, doc_code_files=doc_code_files, real_paths=real_paths
    )


def _languages(files: list[Path]) -> frozenset[str]:
    """The languages a reader reads `files` as."""
    return frozenset(name for name in map(language_read, files) if name is not None)


CODE_HALLUCINATED_DEPENDENCY = "import-deps/hallucinated-dependency"


class DependencyCheck:
    name: ClassVar[str] = "import-deps"
    default_severity: ClassVar[Severity] = Severity.warning
    explanations: ClassVar[dict[str, str]] = {
        CODE_HALLUCINATED_DEPENDENCY: (
            "A `depends_on` entry is declared but no import relationship backs it in "
            "code. It is judged only where an import would have shown it: the two docs "
            "own code of a language in common, and every import of this doc's files of each "
            "such language can be placed. Where a path alias, another package or a missing "
            "manifest may stand between two files, or one of its files does not parse, a "
            "missing import proves nothing and the entry is not judged. Remove the stale "
            "declaration, or verify the doc "
            "claiming the dependent module actually covers the right files."
        ),
    }
    classes: ClassVar[dict[str, FindingClass]] = {
        CODE_HALLUCINATED_DEPENDENCY: FindingClass.hint,
    }
    answers: ClassVar[dict[str, Answer]] = {
        CODE_HALLUCINATED_DEPENDENCY: Answer.fix(
            "remove the `depends_on` entry no import backs, or correct which doc owns the "
            "imported module"
        ),
    }

    def run(self, graph: DocGraph) -> list[Finding]:
        if graph.config is None or graph.repo_root is None:
            return []

        roots = [graph.repo_root / root for root in graph.config.paths.source_roots]
        ownership = resolve_ownership(graph)
        code_files = ownership.doc_code_files

        languages = {doc_id: _languages(files) for doc_id, files in code_files.items()}
        nothing: frozenset[str] = frozenset()

        out: list[Finding] = []
        for node in graph.nodes.values():
            # A dependency on a doc with no language in common is a relationship no
            # missing import denies; judging it would report a true `depends_on` as
            # hallucinated.
            files = code_files.get(node.id, [])
            owned = languages.get(node.id, nothing)
            shared = {
                dep: owned & languages.get(dep, nothing) for dep in node.frontmatter.depends_on
            }
            declared_deps = {dep for dep, common in shared.items() if common}
            if not declared_deps:
                continue

            actual_deps: set[str] = set()
            # The languages of which this doc owns a file whose imports are only partly
            # placed: one of them could hold an import unseen.
            unplaced: set[str] = set()
            for abs_path in files:
                reading = graph.source.reading(abs_path)
                if reading is None:
                    continue
                if not reading.places_every_import(abs_path):
                    unplaced.update(_languages([abs_path]))
                for candidate in imported_files(reading, abs_path, roots):
                    dep_id = ownership.owner_of(candidate)
                    if dep_id and dep_id != node.id:
                        actual_deps.add(dep_id)

            # Intent-only: flag a declared dependency that has no actual
            # import (a hallucinated/stale declaration), but never the reverse —
            # forcing `depends_on` to mirror every import is the materialization
            # pressure the "derive, don't materialize" principle rejects. depends_on
            # is curated intent, not a complete projection of the import graph.
            for dep_id in sorted(declared_deps - actual_deps):
                if shared[dep_id] & unplaced:
                    continue
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
