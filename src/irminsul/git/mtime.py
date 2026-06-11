"""Last-commit-time helpers for source files.

`mtime-drift`, `stale-reaper`, and the external-link cache use these. The
contract is intentionally narrow: pure functions over `Path`s, return `GitTime`
values that tell the caller "no history available" via a None payload rather
than raising. Callers degrade gracefully (warning, skip, fallback to fs mtime)
instead of erroring on tarball checkouts or shallow clones.
"""

from __future__ import annotations

import datetime as _dt
from collections.abc import Generator, Iterable
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path

from git import InvalidGitRepositoryError, NoSuchPathError, Repo


@dataclass(frozen=True)
class GitTime:
    sha: str | None
    when: _dt.datetime | None  # UTC; None when no history is available


_NO_TIME = GitTime(sha=None, when=None)


@contextmanager
def _open_repo(repo_root: Path) -> Generator[Repo | None, None, None]:
    repo: Repo | None = None
    try:
        repo = Repo(repo_root, search_parent_directories=False)
    except (InvalidGitRepositoryError, NoSuchPathError):
        yield None
        return
    if repo.bare or not repo.head.is_valid():
        repo.close()
        yield None
        return
    try:
        yield repo
    finally:
        repo.close()


def has_history(repo_root: Path) -> bool:
    with _open_repo(repo_root) as repo:
        return repo is not None


def is_shallow(repo_root: Path) -> bool:
    """True when this is a shallow clone (e.g. CI fetch-depth=1)."""
    with _open_repo(repo_root) as repo:
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
    with _open_repo(repo_root) as repo:
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

    A path *inside* docs_root may still belong to a nested repository — e.g. a
    private docs repo that the outer (public) code repo gitignores. When the
    outer repo has no history for such a path, the nearest enclosing `.git` is
    consulted before giving up.
    """
    try:
        path.relative_to(docs_root)
    except ValueError:
        root = git_root_for(path)
        if root is None:
            return None
        return last_commit_time(root, path)

    gt = last_commit_time(docs_root, path)
    if gt.when is not None:
        return gt
    nested_root = git_root_for(path)
    if (
        nested_root is None
        or nested_root == docs_root
        or nested_root.resolve() == docs_root.resolve()
    ):
        return gt
    return last_commit_time(nested_root, path)


def diff_name_only(repo_root: Path, base_ref: str, head_ref: str) -> frozenset[str] | None:
    """Repo-relative POSIX paths changed between `base_ref` and `head_ref`.

    Uses the three-dot (merge-base) range and follows renames, so a renamed
    source file shows up once at its destination rather than as an add plus a
    delete. Returns None when the repo has no usable history or either ref
    cannot be resolved — the caller treats that as "no diff coverage" rather
    than an error.
    """
    with _open_repo(repo_root) as repo:
        if repo is None:
            return None
        try:
            out = repo.git.diff("-z", "--name-only", "--find-renames", f"{base_ref}...{head_ref}")
        except Exception:
            return None
    return frozenset(line for line in out.split("\0") if line)


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
