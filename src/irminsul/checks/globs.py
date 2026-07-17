"""Configured source discovery and `describes` glob validation."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import ClassVar, Literal

from pathspec import GitIgnoreSpec

from irminsul.checks.base import Finding, Severity
from irminsul.config import IrminsulConfig
from irminsul.docgraph import DocGraph
from irminsul.git.mtime import git_root_for


@dataclass(frozen=True)
class SourceWalkIssue:
    kind: Literal["broken-symlink", "source-root-escape"]
    root: str
    path: str
    message: str


@dataclass(frozen=True)
class SourceWalkResult:
    files: list[tuple[Path, str]]
    missing_roots: list[str]
    issues: list[SourceWalkIssue]


def walk_source_files(
    repo_root: Path, source_roots: list[str]
) -> tuple[list[tuple[Path, str]], list[str]]:
    """Return ([(abs_path, display_posix)], missing_roots).

    Compatibility adapter using the default source policy. New production
    consumers use `walk_configured_source_files` so explicit config participates.
    A missing root is returned separately rather than raising.

    display_posix is repo-relative for same-repo files and source-root-relative
    for cross-repo files (source_root outside repo_root). Callers use display_posix
    for glob matching and abs_path for git/file I/O.
    """
    result = _walk_source_files(
        repo_root,
        source_roots,
        source_includes=[],
        source_excludes=[],
        honor_gitignore=True,
    )
    return result.files, result.missing_roots


def walk_configured_source_files(
    repo_root: Path,
    config: IrminsulConfig,
) -> SourceWalkResult:
    return _walk_source_files(
        repo_root,
        config.paths.source_roots,
        source_includes=config.paths.source_includes,
        source_excludes=config.paths.source_excludes,
        honor_gitignore=config.paths.honor_gitignore,
    )


def _walk_source_files(
    repo_root: Path,
    source_roots: list[str],
    *,
    source_includes: list[str],
    source_excludes: list[str],
    honor_gitignore: bool,
) -> SourceWalkResult:
    files: list[tuple[Path, str]] = []
    missing: list[str] = []
    issues: list[SourceWalkIssue] = []
    include_spec = GitIgnoreSpec.from_lines(source_includes) if source_includes else None
    exclude_spec = GitIgnoreSpec.from_lines(source_excludes) if source_excludes else None

    for root in source_roots:
        abs_root = (repo_root / root).resolve()
        if not abs_root.is_dir():
            missing.append(root)
            continue
        ignore_matcher = _GitIgnoreMatcher(abs_root) if honor_gitignore else None

        for dirpath, dirnames, filenames in os.walk(abs_root, followlinks=False):
            current = Path(dirpath)
            kept_dirs: list[str] = []
            for name in dirnames:
                path = current / name
                parts = path.relative_to(abs_root).parts
                display = _display_path(path, repo_root, abs_root)
                if path.is_symlink() or _is_excluded(parts):
                    continue
                if _matches(exclude_spec, display, is_dir=True):
                    continue
                if ignore_matcher is not None and ignore_matcher.matches(path, is_dir=True):
                    continue
                kept_dirs.append(name)
            dirnames[:] = kept_dirs

            for name in filenames:
                path = current / name
                parts = path.relative_to(abs_root).parts
                display = _display_path(path, repo_root, abs_root)
                if _is_excluded(parts):
                    continue
                if _matches(exclude_spec, display):
                    continue
                if include_spec is not None and not _matches(include_spec, display):
                    continue
                if ignore_matcher is not None and ignore_matcher.matches(path):
                    continue

                if path.is_symlink():
                    try:
                        target = path.resolve(strict=True)
                    except (OSError, RuntimeError):
                        issues.append(
                            SourceWalkIssue(
                                kind="broken-symlink",
                                root=root,
                                path=display,
                                message=f"source symlink '{display}' has no readable target",
                            )
                        )
                        continue
                    if not _is_within_source_root(target, abs_root):
                        issues.append(
                            SourceWalkIssue(
                                kind="source-root-escape",
                                root=root,
                                path=display,
                                message=(
                                    f"source symlink '{display}' resolves outside configured "
                                    f"root '{root}'"
                                ),
                            )
                        )
                        continue
                    if not target.is_file():
                        continue
                elif not path.is_file():
                    continue

                files.append((path, display))

    files.sort(key=lambda item: item[1])
    issues.sort(key=lambda issue: (issue.path, issue.kind))
    return SourceWalkResult(files=files, missing_roots=missing, issues=issues)


def _display_path(path: Path, repo_root: Path, source_root: Path) -> str:
    try:
        relative = path.relative_to(repo_root.resolve())
    except ValueError:
        relative = path.relative_to(source_root)
    return PurePosixPath(*relative.parts).as_posix()


def _is_within_source_root(target: Path, source_root: Path) -> bool:
    return target.resolve(strict=False).is_relative_to(source_root.resolve())


def _matches(spec: GitIgnoreSpec | None, display: str, *, is_dir: bool = False) -> bool:
    if spec is None:
        return False
    candidate = f"{display.rstrip('/')}" + ("/" if is_dir else "")
    return bool(spec.match_file(candidate))


class _GitIgnoreMatcher:
    def __init__(self, source_root: Path) -> None:
        self.source_root = source_root
        self.boundary = git_root_for(source_root) or source_root
        if not source_root.is_relative_to(self.boundary):
            self.boundary = source_root
        self._cache: dict[Path, GitIgnoreSpec | None] = {}

    def matches(self, path: Path, *, is_dir: bool = False) -> bool:
        parent = path.parent
        try:
            relative_parent = parent.relative_to(self.boundary)
        except ValueError:
            return False

        directories = [self.boundary]
        current = self.boundary
        for part in relative_parent.parts:
            current /= part
            directories.append(current)

        ignored: bool | None = None
        for directory in directories:
            spec = self._spec_for(directory)
            if spec is None:
                continue
            relative = path.relative_to(directory).as_posix()
            if is_dir:
                relative = f"{relative.rstrip('/')}" + "/"
            result = spec.check_file(relative)
            if result.include is not None:
                ignored = result.include
        return ignored is True

    def _spec_for(self, directory: Path) -> GitIgnoreSpec | None:
        if directory in self._cache:
            return self._cache[directory]

        ignore_file = directory / ".gitignore"
        if not ignore_file.is_file():
            self._cache[directory] = None
            return None

        lines = ignore_file.read_text(encoding="utf-8", errors="replace").splitlines()
        if directory != self.source_root and self.source_root.is_relative_to(directory):
            root_relative = self.source_root.relative_to(directory).as_posix()
            lines = [
                line for line in lines if not _pattern_ignores_explicit_root(line, root_relative)
            ]
        spec = GitIgnoreSpec.from_lines(lines)
        self._cache[directory] = spec
        return spec


def _pattern_ignores_explicit_root(pattern: str, root_relative: str) -> bool:
    result = GitIgnoreSpec.from_lines([pattern]).check_file(f"{root_relative.rstrip('/')}/")
    return result.include is True


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
    """Compatibility path classifier with built-in exclusions only."""
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


def is_configured_source_path(
    repo_root: Path,
    config: IrminsulConfig,
    display: str,
) -> bool:
    normalized = PurePosixPath(display.replace("\\", "/")).as_posix()
    include_spec = (
        GitIgnoreSpec.from_lines(config.paths.source_includes)
        if config.paths.source_includes
        else None
    )
    exclude_spec = (
        GitIgnoreSpec.from_lines(config.paths.source_excludes)
        if config.paths.source_excludes
        else None
    )
    if _matches(exclude_spec, normalized):
        return False
    if include_spec is not None and not _matches(include_spec, normalized):
        return False

    path = PurePosixPath(normalized)
    repo_abs = repo_root.resolve()
    for root in config.paths.source_roots:
        abs_root = (repo_abs / root).resolve()
        try:
            root_relative = abs_root.relative_to(repo_abs)
        except ValueError:
            continue
        prefix = PurePosixPath(*root_relative.parts)
        if prefix.parts:
            if not path.is_relative_to(prefix):
                continue
            parts = path.relative_to(prefix).parts
        else:
            parts = path.parts
        if not parts or _is_excluded(parts):
            continue

        candidate = (repo_abs / Path(*path.parts)).resolve(strict=False)
        if not candidate.is_relative_to(abs_root):
            continue
        if config.paths.honor_gitignore and _GitIgnoreMatcher(abs_root).matches(candidate):
            continue
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

        result = walk_configured_source_files(graph.repo_root, graph.config)
        source_files = result.files

        out: list[Finding] = []

        for root in result.missing_roots:
            out.append(
                Finding(
                    check=self.name,
                    severity=Severity.warning,
                    message=f"source root '{root}' does not exist",
                )
            )

        for issue in result.issues:
            out.append(
                Finding(
                    check=self.name,
                    severity=(
                        Severity.error if issue.kind == "source-root-escape" else Severity.warning
                    ),
                    message=issue.message,
                    path=Path(issue.path),
                    data={"problem": issue.kind, "source_root": issue.root},
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
