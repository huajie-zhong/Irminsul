"""Last-commit-time helpers for source files.

`mtime-drift`, `stale-reaper`, and the external-link cache use these. The
contract is intentionally narrow: pure functions over `Path`s, return `GitTime`
values that tell the caller "no history available" via a None payload rather
than raising. Callers degrade gracefully (warning, skip, fallback to fs mtime)
instead of erroring on tarball checkouts or shallow clones.
"""

from __future__ import annotations

import datetime as _dt
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path

from git import InvalidGitRepositoryError, NoSuchPathError, Repo


@dataclass(frozen=True)
class GitTime:
    sha: str | None
    when: _dt.datetime | None  # UTC; None when no history is available


_NO_TIME = GitTime(sha=None, when=None)


def _open_repo(repo_root: Path) -> Repo | None:
    try:
        repo = Repo(repo_root, search_parent_directories=False)
    except (InvalidGitRepositoryError, NoSuchPathError):
        return None
    if repo.bare or not repo.head.is_valid():
        return None
    return repo


def has_history(repo_root: Path) -> bool:
    return _open_repo(repo_root) is not None


def is_shallow(repo_root: Path) -> bool:
    """True when this is a shallow clone (e.g. CI fetch-depth=1)."""
    repo = _open_repo(repo_root)
    if repo is None:
        return False
    return (Path(repo.git_dir) / "shallow").exists()


def _commit_to_gittime(commit: object) -> GitTime:
    # gitpython's Commit type lacks public attributes typed for mypy; cast via getattr.
    sha = str(getattr(commit, "hexsha", None) or "") or None
    when = getattr(commit, "committed_datetime", None)
    if when is None:
        return _NO_TIME
    when = when.astimezone(_dt.UTC) if when.tzinfo else when.replace(tzinfo=_dt.UTC)
    return GitTime(sha=sha, when=when)


def last_commit_time(repo_root: Path, path: Path) -> GitTime:
    """Return the last commit that touched `path` (repo-relative or absolute).

    When no git history exists, when `path` has never been committed, or when
    the repo is bare, returns `GitTime(None, None)`.
    """
    repo = _open_repo(repo_root)
    if repo is None:
        return _NO_TIME

    rel = path
    try:
        if path.is_absolute():
            rel = path.relative_to(repo_root)
    except ValueError:
        return _NO_TIME

    try:
        commits = list(repo.iter_commits(paths=str(rel.as_posix()), max_count=1))
    except Exception:
        return _NO_TIME
    if not commits:
        return _NO_TIME
    return _commit_to_gittime(commits[0])


def git_root_for(path: Path) -> Path | None:
    """Walk up from path to find a directory containing a .git entry."""
    cur = path if path.is_dir() else path.parent
    for candidate in (cur, *cur.parents):
        if (candidate / ".git").exists():
            return candidate
    return None


def last_commit_time_any_repo(path: Path, docs_root: Path) -> GitTime | None:
    """Like last_commit_time but handles cross-repo absolute paths.

    Returns None when path is outside docs_root and no .git is found — caller
    should emit an error Finding. Returns _NO_TIME when git exists but path has
    no commits (same as same-repo behaviour).
    """
    try:
        path.relative_to(docs_root)
        return last_commit_time(docs_root, path)
    except ValueError:
        root = git_root_for(path)
        if root is None:
            return None
        return last_commit_time(root, path)


def last_commit_time_for_paths(repo_root: Path, paths: Iterable[Path]) -> GitTime:
    """Maximum (latest) GitTime across `paths`. None when none of the paths
    have any committed history."""
    latest: GitTime = _NO_TIME
    for path in paths:
        gt = last_commit_time(repo_root, path)
        if gt.when is None:
            continue
        if latest.when is None or gt.when > latest.when:
            latest = gt
    return latest
