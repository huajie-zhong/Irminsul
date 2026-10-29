"""The diff range a run judges, resolved once from git and carried on the graph.

`check --diff <base>` names it. Every pass that judges the change rather than the tree —
`co-change`, `diff-integrity` and `new-dependency` — reads it from `DocGraph.change`, so
no two of them can be handed different ideas of what changed. A graph without one is a run that judges the tree alone: every run not
given `--diff`, and the base pass of `--delta`, so what those passes report is never
pre-existing.

The range runs from the merge base of `<base>` and `HEAD` to the working tree, so work
not yet committed is judged as the commit that will carry it. `--committed-only` ends it
at `HEAD`. A clean tree gives the same range either way.
"""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path

from irminsul.config import IrminsulConfig
from irminsul.docgraph import ChangeRange
from irminsul.errors import UserError
from irminsul.git.changes import (
    ChangedPaths,
    GitChangesError,
    changed_since,
    file_at_ref,
    files_at_ref,
)
from irminsul.git.mtime import has_history
from irminsul.git.reader import GitReader


class ChangeRangeError(UserError):
    """The range cannot be computed. A gate that read an empty change set instead would
    pass everything, so the caller exits rather than running without one."""


def resolve_change_range(
    repo_root: Path,
    config: IrminsulConfig,
    base: str,
    source_refs: Mapping[str | None, str] | None = None,
    *,
    committed_only: bool = False,
) -> ChangeRange:
    """The range from the merge base of `base` and `HEAD` to the working tree, or to `HEAD`
    under `committed_only`, plus each sibling source repository's own range when
    `source_refs` names one."""
    git = GitReader()
    since = changed_since(git, repo_root, base, committed_only=committed_only)
    if since is None:
        raise ChangeRangeError(_diff_failure_reason(git, repo_root, base))
    source_changed: frozenset[str] = frozenset()
    if source_refs:
        from irminsul.adoption import source_changed_displays

        source_changed, unreadable_roots = source_changed_displays(
            repo_root, config, source_refs, committed_only=committed_only
        )
        if unreadable_roots:
            raise ChangeRangeError(
                "could not read a source change set for "
                + ", ".join(repr(root) for root in unreadable_roots)
                + ". A gate that reads an empty change set passes "
                "everything, so this exits rather than reporting a clean run; check the "
                "checkout has that ref and full history."
            )
    return range_of(base, since, source_changed, committed_only=committed_only)


def range_of(
    base: str,
    since: ChangedPaths,
    source_changed: frozenset[str] = frozenset(),
    *,
    committed_only: bool = False,
) -> ChangeRange:
    """The range that `since`, read from `base`, describes."""
    return ChangeRange(
        base=base,
        head="HEAD" if committed_only else None,
        changed=since.changed,
        merge_base=since.merge_base,
        uncommitted=since.uncommitted,
        source_changed=source_changed,
    )


def after_text(git: GitReader, repo_root: Path, head: str | None, path: str) -> str | None:
    """A file as the change leaves it, or None when it is absent or unreadable there.

    `head` is a range's end: None for the working tree, else the commit to read. Every
    reader of the after side asks here, so a pass reads the side the changed set was
    measured to.
    """
    if head is None:
        try:
            return (repo_root / path).read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            return None
    try:
        return file_at_ref(git, repo_root, head, path)
    except GitChangesError:
        return None


def after_paths(git: GitReader, repo_root: Path, head: str | None, directory: str) -> list[str]:
    """The files under `directory` as the change leaves them, sorted.

    In the working tree these are the files git tracks or would add, so one that gitignore
    excludes is not part of the change, and a tracked file deleted from disk is not listed.
    """
    folder = directory.strip("/")
    if head is not None:
        try:
            return files_at_ref(git, repo_root, head, folder)
        except GitChangesError:
            return []
    if not folder:
        return []
    listing = git.text_live(
        repo_root, "ls-files", "--cached", "--others", "--exclude-standard", "-z", "--", folder
    )
    if listing is None:
        return []
    return sorted({path for path in listing.split("\0") if path and (repo_root / path).is_file()})


def _diff_failure_reason(git: GitReader, repo_root: Path, base: str) -> str:
    if not has_history(git, repo_root):
        return (
            f"no git repository with commit history found at {repo_root}; "
            "co-change needs one to diff against"
        )
    return (
        f"could not compute `git diff {base}...HEAD`; "
        "at least one ref could not be resolved in this repository"
    )
