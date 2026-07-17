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

from git import GitCommandError, InvalidGitRepositoryError, NoSuchPathError, Repo

from irminsul.baseline import finding_fingerprint
from irminsul.checks.base import Finding


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

    scratch_parent = Path(tempfile.mkdtemp(prefix="irminsul-delta-"))
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
