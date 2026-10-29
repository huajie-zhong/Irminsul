"""Apply deterministic fixes emitted by checks."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from irminsul.atomic import write_atomic
from irminsul.checks.base import Fix


@dataclass(frozen=True)
class FixResult:
    written: list[Path] = field(default_factory=list)
    planned: list[Fix] = field(default_factory=list)
    held: list[Fix] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)


def apply_fixes(
    repo_root: Path,
    fixes: list[Fix],
    *,
    dry_run: bool,
    confirm: bool = False,
) -> FixResult:
    """Apply fixes grouped by path.

    Fix paths are repo-relative. Writes use a same-directory temporary file and
    atomic replace so an interrupted run does not leave partial markdown. A fix sees
    the text with LF endings, and the file is written back with the endings most of
    its lines had, so a CRLF working copy stays CRLF. Fixes tagged `requires_confirm`
    (irreversible edits to load-bearing metadata or prose) are held back unless
    `confirm` is set.
    """
    planned = [fix for fix in fixes if confirm or not fix.requires_confirm]
    held = [fix for fix in fixes if fix.requires_confirm and not confirm]

    grouped: dict[Path, list[Fix]] = {}
    for fix in planned:
        grouped.setdefault(fix.path, []).append(fix)

    written: list[Path] = []
    errors: list[str] = []

    if dry_run:
        return FixResult(planned=planned, held=held)

    for rel_path, path_fixes in sorted(grouped.items(), key=lambda item: item[0].as_posix()):
        abs_path = repo_root / rel_path
        try:
            if not abs_path.exists() and all(fix.creates for fix in path_fixes):
                text = ""
            else:
                text = abs_path.read_bytes().decode("utf-8").replace("\r\n", "\n")
            updated = text
            for fix in path_fixes:
                updated = fix.apply(updated)
            if updated == text:
                continue
            write_atomic(abs_path, updated)
            written.append(rel_path)
        except Exception as exc:
            errors.append(f"{rel_path.as_posix()}: {type(exc).__name__}: {exc}")

    return FixResult(written=written, planned=planned, held=held, errors=errors)
