"""Apply deterministic fixes emitted by checks."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

from irminsul.checks.base import Fix


@dataclass(frozen=True)
class FixResult:
    written: list[Path] = field(default_factory=list)
    planned: list[Fix] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)


def apply_fixes(
    repo_root: Path,
    fixes: list[Fix],
    *,
    dry_run: bool,
) -> FixResult:
    """Apply fixes grouped by path.

    Fix paths are repo-relative. Writes use a same-directory temporary file and
    atomic replace so an interrupted run does not leave partial markdown.
    """
    grouped: dict[Path, list[Fix]] = {}
    for fix in fixes:
        grouped.setdefault(fix.path, []).append(fix)

    written: list[Path] = []
    errors: list[str] = []

    if dry_run:
        return FixResult(planned=fixes)

    for rel_path, path_fixes in sorted(grouped.items(), key=lambda item: item[0].as_posix()):
        abs_path = repo_root / rel_path
        try:
            text = abs_path.read_text(encoding="utf-8")
            updated = text
            for fix in path_fixes:
                updated = fix.apply(updated)
            if updated == text:
                continue
            tmp_path = abs_path.with_name(f"{abs_path.name}.tmp")
            tmp_path.write_text(updated, encoding="utf-8")
            os.replace(tmp_path, abs_path)
            written.append(rel_path)
        except Exception as exc:
            errors.append(f"{rel_path.as_posix()}: {type(exc).__name__}: {exc}")

    return FixResult(written=written, planned=fixes, errors=errors)
