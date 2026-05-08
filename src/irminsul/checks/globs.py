"""GlobsCheck — every `describes` pattern must resolve to ≥1 source file."""

from __future__ import annotations

from pathlib import Path, PurePosixPath
from typing import ClassVar

from pathspec import GitIgnoreSpec

from irminsul.checks.base import Finding, Severity
from irminsul.docgraph import DocGraph


def _walk_source_files(repo_root: Path, source_roots: list[str]) -> tuple[list[str], list[str]]:
    """Return (relative_posix_paths, missing_roots).

    Walks every file under each existing source root. Skips dot-directories
    (`.git`, `.venv`, `.mypy_cache`, ...) so we don't drag environment cruft
    into the source set. A missing root isn't fatal here — surfaced separately
    so the caller can warn rather than error.
    """
    files: list[str] = []
    missing: list[str] = []
    for root in source_roots:
        abs_root = (repo_root / root).resolve()
        if not abs_root.exists():
            missing.append(root)
            continue
        for path in abs_root.rglob("*"):
            if not path.is_file():
                continue
            if any(part.startswith(".") for part in path.relative_to(repo_root).parts):
                continue
            rel = PurePosixPath(*path.relative_to(repo_root).parts)
            files.append(str(rel))
    return files, missing


class GlobsCheck:
    name: ClassVar[str] = "globs"
    default_severity: ClassVar[Severity] = Severity.error

    def run(self, graph: DocGraph) -> list[Finding]:
        if graph.config is None or graph.repo_root is None:
            return []

        source_files, missing_roots = _walk_source_files(
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
                if not any(spec.match_file(f) for f in source_files):
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
