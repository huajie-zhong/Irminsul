"""Last-commit-time helpers for source files.

`mtime-drift`, `stale-reaper`, and the external-link cache use these. The
contract is intentionally narrow: pure functions over `Path`s, return `GitTime`
values that tell the caller "no history available" via a None payload rather
than raising. Callers degrade gracefully (warning, skip, fallback to fs mtime)
instead of erroring on tarball checkouts or shallow clones.
"""

from __future__ import annotations

import datetime as _dt
import re
from collections.abc import Generator, Iterable
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path, PurePosixPath

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


_LOG_HEADER_RE = re.compile(r"^([0-9a-f]{40,64}) (\d+)$")

_bulk_cache: dict[Path, dict[str, GitTime]] = {}


def _parse_bulk_log(raw: str) -> dict[str, GitTime]:
    """Parse `git log --name-only -z --format='%H %ct'` output into a
    path -> latest-GitTime map.

    With `-z`, each commit header is NUL-terminated, and (when the commit has
    a file list) so is each file name; the first file name additionally
    carries a leading `\\n` left over from the header/file-list separator that
    plain (non -z) `git log` prints as a blank line. Splitting the whole
    stream on NUL and stripping that leading `\\n` recovers header vs. file
    tokens unambiguously — a header token always matches the strict
    `<hex sha> <digits>` shape, which a real path cannot.
    """
    times: dict[str, GitTime] = {}
    current: GitTime | None = None
    for token in raw.split("\0"):
        if not token:
            continue
        if token[0] == "\n":
            path = token[1:]
            if path and current is not None:
                times.setdefault(path, current)
            continue
        header = _LOG_HEADER_RE.match(token)
        if header is not None:
            when = _dt.datetime.fromtimestamp(int(header.group(2)), tz=_dt.UTC)
            current = GitTime(sha=header.group(1), when=when)
            continue
        if current is not None:
            times.setdefault(token, current)
    return times


def bulk_last_commit_times(repo_root: Path) -> dict[str, GitTime]:
    """One `git log` pass over `repo_root`: repo-relative POSIX path -> its
    latest GitTime, replacing one `last_commit_time` call per path with a
    single subprocess for the whole repo.

    Walking newest-first, the first commit that lists a path is that path's
    most recent touch — matching `last_commit_time`'s per-path answer for
    ordinary commits. Merge commits carry no file list under plain
    `--name-only` (same as everyday `git log`), so a path whose only recent
    change came from a merge's own conflict resolution resolves to its latest
    non-merge ancestor instead — an accepted tradeoff for the O(1)-subprocess
    win.

    Cached per repo root for the life of the process: opening and closing a
    `Repo` just to check "did HEAD move" is itself far costlier than the
    `git log` call it would guard, so a plain process-lifetime cache (as
    opposed to one keyed on HEAD sha) is the one that's actually cheap on
    every lookup, not just the first.
    """
    key = repo_root.resolve()
    cached = _bulk_cache.get(key)
    if cached is not None:
        return cached

    with _open_repo(repo_root) as repo:
        if repo is None:
            _bulk_cache[key] = {}
            return _bulk_cache[key]
        try:
            raw = repo.git.log("--name-only", "-z", "--format=%H %ct")
        except Exception:
            _bulk_cache[key] = {}
            return _bulk_cache[key]

    times = _parse_bulk_log(raw)
    _bulk_cache[key] = times
    return times


def _bulk_lookup(repo_root: Path, path: Path) -> GitTime:
    rel = path
    if path.is_absolute():
        try:
            rel = path.relative_to(repo_root)
        except ValueError:
            return _NO_TIME
    key = PurePosixPath(*rel.parts).as_posix()
    return bulk_last_commit_times(repo_root).get(key, _NO_TIME)


def last_commit_time_any_repo(path: Path, docs_root: Path) -> GitTime | None:
    """Like last_commit_time but handles cross-repo absolute paths.

    Returns None when path is outside docs_root and no .git is found — caller
    should emit an error Finding. Returns _NO_TIME when git exists but path has
    no commits (same as same-repo behaviour).

    A path *inside* docs_root may still belong to a nested repository — e.g. a
    private docs repo that the outer (public) code repo gitignores. The nearest
    enclosing `.git` is authoritative so stale history from a former outer-repo
    location cannot override the nested repository.
    """
    try:
        path.relative_to(docs_root)
    except ValueError:
        root = git_root_for(path)
        if root is None:
            return None
        return _bulk_lookup(root, path)

    nested_root = git_root_for(path)
    if (
        nested_root is None
        or nested_root == docs_root
        or nested_root.resolve() == docs_root.resolve()
    ):
        return _bulk_lookup(docs_root, path)
    return _bulk_lookup(nested_root, path)


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
