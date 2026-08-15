"""`check --delta`: report only findings introduced by the working tree.

Mechanism: check out the base rev into a scratch `git worktree`, run the same
configured checks there, and keep only worktree findings whose fingerprint
(check, path, message — see `irminsul.baseline`) does not appear in the base
run. Reuses baseline's fingerprint so "new" means the same thing under
`--delta` as it does under the baseline ratchet.

The scratch worktree lives under the system temp dir, never inside the
target repo, and is removed unconditionally. `git worktree add --detach`
never touches the caller's working tree or index.
"""

from __future__ import annotations

import shutil
import tempfile
import time
from collections.abc import Generator
from contextlib import contextmanager, suppress
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

from git import GitCommandError, InvalidGitRepositoryError, NoSuchPathError, Repo

from irminsul.baseline import finding_fingerprint
from irminsul.checks.base import Finding
from irminsul.git.mtime import git_root_for

if TYPE_CHECKING:
    from irminsul.config import IrminsulConfig


class DeltaError(Exception):
    """Raised when `--delta` cannot produce a base-rev comparison."""


@dataclass(frozen=True)
class DeltaResult:
    new: list[Finding]
    pre_existing: int


def compute_delta(worktree_findings: list[Finding], base_findings: list[Finding]) -> DeltaResult:
    """Split worktree findings into new (not in the base run) and pre-existing.

    All severities are compared the same way — unlike the baseline ratchet,
    info findings are not special-cased, since delta's job is "did this diff
    cause it", not "is it debt worth tracking".
    """
    base_fingerprints = {finding_fingerprint(f) for f in base_findings}
    new: list[Finding] = []
    pre_existing = 0
    for finding in worktree_findings:
        if finding_fingerprint(finding) in base_fingerprints:
            pre_existing += 1
        else:
            new.append(finding)
    return DeltaResult(new=new, pre_existing=pre_existing)


def cross_repo_trees(repo_root: Path, config: IrminsulConfig) -> list[str]:
    """Configured trees owned by a git repository other than `repo_root`'s.

    `git worktree add` checks out tracked files only, so a tree that belongs to
    another repository is simply absent from the base checkout. In the siblings
    layout that is the code repo `source_roots` reach through `../`. Checked per
    configured root rather than by scanning the tree, so an unrelated vendored
    checkout never trips it.

    A configured root that is missing on disk is skipped — the source walk
    already reports it, and its absence says nothing about the layout.
    """
    own_root = git_root_for(repo_root)
    if own_root is None:
        return []
    own_resolved = own_root.resolve()
    outside: list[str] = []
    for rel in (config.paths.docs_root, *config.paths.source_roots):
        tree = (repo_root / rel).resolve()
        if not tree.is_dir():
            continue
        owner = git_root_for(tree)
        if owner is None or owner.resolve() != own_resolved:
            outside.append(rel)
    return outside


def verify_single_repo_topology(repo_root: Path, config: IrminsulConfig) -> None:
    """Raise `DeltaError` when `--delta` would silently compare against a tree
    the base checkout cannot contain.

    Of the two supported layouts this guards exactly one: `siblings`, where the
    code repo is a separate git repository that `git worktree add` cannot
    reproduce. Without the guard the base run finds nothing under those roots,
    so every finding over them survives as "new" — the exact inversion of what
    `--delta` promises, delivered with a nonzero exit and no warning.

    Teaching `--delta` to compare across the sibling boundary is open work; the
    seam is here, and it is the only place the refusal is decided.
    """
    outside = cross_repo_trees(repo_root, config)
    if not outside:
        return
    roots = ", ".join(repr(r) for r in outside)
    raise DeltaError(
        f"--delta does not support the siblings layout yet: {roots} "
        f"belong(s) to a different git repository than {repo_root}. "
        "`git worktree add` checks out tracked files only, so the base "
        "checkout would omit them and every finding over them would be "
        "reported as new. Re-run `check` without --delta, and use mtime-drift "
        "as the cross-repository signal."
    )


@contextmanager
def pristine_checkout(repo_root: Path, rev: str) -> Generator[Path, None, None]:
    """Check out `rev` into a scratch `git worktree` and yield its root.

    `repo_root` must itself be a git worktree root (mirrors `--diff`'s
    `_open_repo` contract: no parent-directory search). The scratch worktree
    is removed in a `finally` block even if the caller raises.
    """
    try:
        repo = Repo(repo_root, search_parent_directories=False)
    except (InvalidGitRepositoryError, NoSuchPathError) as e:
        raise DeltaError(
            f"no git repository with commit history found at {repo_root}; "
            "--delta needs one to check out --delta-base"
        ) from e

    # Resolve the temp root: the system temp dir is a symlink on macOS
    # (/var -> /private/var) and can be an 8.3 short name on Windows, while the
    # doc walk yields fully resolved paths. An unresolved root here makes
    # `parse_doc`'s `relative_to(repo_root)` raise for every doc it finds.
    scratch_parent = Path(tempfile.mkdtemp(prefix="irminsul-delta-")).resolve()
    scratch_dir = scratch_parent / "base"
    try:
        try:
            repo.git.worktree("add", "--detach", str(scratch_dir), rev)
        except GitCommandError as e:
            raise DeltaError(f"could not check out --delta-base {rev!r}: {e}") from e
        try:
            yield scratch_dir
        finally:
            _remove_worktree(repo, scratch_dir)
    finally:
        repo.close()
        shutil.rmtree(scratch_parent, ignore_errors=True)


def _remove_worktree(repo: Repo, scratch_dir: Path) -> None:
    """Best-effort, retrying removal. Windows can hold file-lock handles open
    briefly after a checkout, so a plain `worktree remove` can transiently
    fail; retry with backoff, then fall back to `worktree prune` so the main
    repo's `.git/worktrees` metadata never leaks a stale entry."""
    attempts = 5
    for attempt in range(attempts):
        try:
            repo.git.worktree("remove", "--force", str(scratch_dir))
            return
        except GitCommandError:
            if attempt == attempts - 1:
                break
            time.sleep(0.2 * (attempt + 1))
    with suppress(GitCommandError):
        repo.git.worktree("prune")
