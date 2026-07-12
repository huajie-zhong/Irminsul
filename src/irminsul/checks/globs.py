"""GlobsCheck — every `describes` pattern must resolve to ≥1 source file."""

from __future__ import annotations

from pathlib import Path, PurePosixPath
from typing import ClassVar

from pathspec import GitIgnoreSpec

from irminsul.checks.base import Finding, Severity
from irminsul.docgraph import DocGraph


def walk_source_files(
    repo_root: Path, source_roots: list[str]
) -> tuple[list[tuple[Path, str]], list[str]]:
    """Return ([(abs_path, display_posix)], missing_roots).

    Walks every file under each existing source root. Skips dot-directories
    (`.git`, `.venv`, `.mypy_cache`, ...). A missing root isn't fatal here —
    surfaced separately so the caller can warn rather than error.

    display_posix is repo-relative for same-repo files and source-root-relative
    for cross-repo files (source_root outside repo_root). Callers use display_posix
    for glob matching and abs_path for git/file I/O.
    """
    files: list[tuple[Path, str]] = []
    missing: list[str] = []
    for root in source_roots:
        abs_root = (repo_root / root).resolve()
        if not abs_root.exists():
            missing.append(root)
            continue
        for path in abs_root.rglob("*"):
            if not path.is_file():
                continue
            if _is_excluded(path.relative_to(abs_root).parts):
                continue
            try:
                display = str(PurePosixPath(*path.relative_to(repo_root).parts))
            except ValueError:
                display = str(PurePosixPath(*path.relative_to(abs_root).parts))
            files.append((path, display))
    return files, missing


def source_root_prefixes(repo_root: Path, source_roots: list[str]) -> list[str]:
    """Repo-relative POSIX prefixes of the source roots that live inside the repo.

    An empty string means the repo root itself. Roots outside the repo (the
    sibling code repo of Topology A/B) are omitted: a repo-relative diff path
    can never fall under them, and their on-disk files already carry a
    source-root-relative display from `walk_source_files`.
    """
    prefixes: list[str] = []
    root_abs = repo_root.resolve()
    for root in source_roots:
        try:
            rel = (repo_root / root).resolve().relative_to(root_abs)
        except ValueError:
            continue
        prefixes.append(PurePosixPath(*rel.parts).as_posix() if rel.parts else "")
    return prefixes


def is_source_path(display: str, prefixes: list[str]) -> bool:
    """Whether a repo-relative POSIX path would be walked as a source file.

    The disk-walk answer for a path that still exists, and the only answer
    available for one that was deleted — a deletion is still a change to the
    component that owned the file.
    """
    path = PurePosixPath(display.replace("\\", "/"))
    for prefix in prefixes:
        if prefix:
            if not path.is_relative_to(prefix):
                continue
            parts = path.relative_to(prefix).parts
        else:
            parts = path.parts
        if parts and not _is_excluded(parts):
            return True
    return False


def _is_excluded(parts: tuple[str, ...]) -> bool:
    if any(part.startswith(".") or part == "__pycache__" for part in parts):
        return True
    return PurePosixPath(parts[-1]).suffix in {".pyc", ".pyo"}


class GlobsCheck:
    name: ClassVar[str] = "globs"
    default_severity: ClassVar[Severity] = Severity.error

    def run(self, graph: DocGraph) -> list[Finding]:
        if graph.config is None or graph.repo_root is None:
            return []

        source_files, missing_roots = walk_source_files(
            graph.repo_root, graph.config.paths.source_roots
        )

        out: list[Finding] = []

        for root in missing_roots:
            out.append(
                Finding(
                    check=self.name,
                    severity=Severity.warning,
                    message=f"source root '{root}' does not exist",
                )
            )

        for node in graph.nodes.values():
            for pattern in node.frontmatter.describes:
                spec = GitIgnoreSpec.from_lines([pattern])
                if not any(spec.match_file(display) for _, display in source_files):
                    out.append(
                        Finding(
                            check=self.name,
                            severity=Severity.error,
                            message=(f"describes pattern '{pattern}' matched zero files"),
                            path=node.path,
                            doc_id=node.id,
                        )
                    )

        return out
