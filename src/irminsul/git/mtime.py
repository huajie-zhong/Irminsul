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
import subprocess
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path, PurePosixPath


@dataclass(frozen=True)
class GitTime:
    sha: str | None
    when: _dt.datetime | None  # UTC; None when no history is available


_NO_TIME = GitTime(sha=None, when=None)


def _git_text(repo_root: Path, *args: str) -> str | None:
    """Stdout of a git command, or None when it fails.

    Plain `subprocess` rather than GitPython: GitPython keeps the process it spawned
    alive behind the returned string, and on Windows those handles outlive the call —
    enough for Python 3.13's unraisable hook to surface "subprocess is still running"
    as a `ResourceWarning`, which this project's `filterwarnings = ["error"]` turns
    into a failure.
    """
    try:
        result = subprocess.run(
            ["git", "-C", str(repo_root), *args],
            check=False,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
    except OSError:
        # git absent from PATH is a FileNotFoundError; this module's contract is to
        # report "no history available" rather than to raise.
        return None
    return result.stdout if result.returncode == 0 else None


def has_history(repo_root: Path) -> bool:
    return history_state(repo_root)[0]


def is_shallow(repo_root: Path) -> bool:
    """True when this is a shallow clone (e.g. CI fetch-depth=1)."""
    return history_state(repo_root)[1]


def history_state(repo_root: Path) -> tuple[bool, bool]:
    """(has history, is shallow) — whether this checkout can answer git questions.

    One `git rev-parse` rather than two repository opens: every `irminsul check` asks
    this, and opening the repository twice through GitPython cost about a third of a
    second on a repository of any size.
    """
    stdout = _git_text(
        repo_root,
        "rev-parse",
        # `--git-common-dir`, not `--git-dir`: inside a linked worktree the latter is
        # `<main>/.git/worktrees/<name>`, which never holds the `shallow` marker, so a
        # worktree of a shallow clone reported full history. `pristine_checkout` builds
        # exactly such a worktree.
        "--git-common-dir",
        "--show-toplevel",
        "--is-bare-repository",
        "--verify",
        "-q",
        "HEAD",
    )
    if stdout is None:
        return False, False
    # `splitlines`, not `split`: a repository path containing a space is ordinary
    # on Windows ("C:/Users/Jane Doe/proj") and splitting on whitespace tears it
    # in half, which reads as a repository with no history at all.
    lines = stdout.splitlines()
    if len(lines) < 4 or lines[2] == "true":
        return False, False
    # `rev-parse` walks up to the nearest repository; this question is about the
    # directory itself, so a subdirectory of a repository does not count.
    try:
        if Path(lines[1]).resolve() != repo_root.resolve():
            return False, False
    except OSError:
        return False, False
    git_dir = Path(lines[0])
    if not git_dir.is_absolute():
        git_dir = repo_root / git_dir
    return True, (git_dir / "shallow").exists()


def last_commit_time(repo_root: Path, path: Path) -> GitTime:
    """Return the last commit that touched `path` (repo-relative or absolute).

    When no git history exists, when `path` has never been committed, or when
    the repo is bare, returns `GitTime(None, None)`.
    """
    rel = path
    try:
        if path.is_absolute():
            rel = path.relative_to(repo_root)
    except ValueError:
        return _NO_TIME

    # `iter_commits` hands back a generator backed by a live git process, which is the
    # same handle leak `_git_text` exists to avoid.
    raw = _git_text(repo_root, "log", "-1", "--format=%H %ct", "--", rel.as_posix())
    if not raw or not raw.strip():
        return _NO_TIME
    sha, _, when = raw.strip().partition(" ")
    if not when.strip().isdigit():
        return _NO_TIME
    return GitTime(sha=sha, when=_dt.datetime.fromtimestamp(int(when.strip()), tz=_dt.UTC))


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

    Cached per repo root until `forget_git_history` runs, which `build_graph` does
    for every new graph. Asking git whether HEAD moved on each lookup would cost a
    subprocess per path, far more than the one `git log` it guards, so the cache is
    bounded by the graph instead: one invocation reads history once, and the next
    invocation — including the next call to a long-running MCP server — reads it again.
    """
    key = repo_root.resolve()
    cached = _bulk_cache.get(key)
    if cached is not None:
        return cached

    raw = _git_text(repo_root, "log", "--name-only", "-z", "--format=%H %ct")
    if raw is None or not has_history(repo_root):
        _bulk_cache[key] = {}
        return _bulk_cache[key]

    times = _parse_bulk_log(raw)
    _bulk_cache[key] = times
    return times


def forget_git_history() -> None:
    """Drop every cached `git log` so the next lookup reads history again."""
    _bulk_cache.clear()


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

    `docs_root` here is the directory irminsul was invoked from — the one that
    owns `irminsul.toml` — which is not necessarily a repository root. The
    common case that makes the last line load-bearing is a monorepo subfolder:
    irminsul runs from `packages/proj/`, the `.git` sits above at the monorepo
    root, and `git_root_for` walks *up* to find it. The enclosing root is then
    an **ancestor** of `docs_root`, not a descendant, and it is the only repo
    that has any history for the path — asking `docs_root` instead returns
    GitTime(None, None) and every git time silently disappears. Irminsul's own
    fixture repos take this path, since they live inside this git repo.

    The same line also covers a repository *below* `docs_root` (a submodule or
    vendored checkout carrying its own `.git`). Either way the nearest enclosing
    `.git` is authoritative, so history from the wrong repository — stale or
    absent — cannot override it.
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
    if not has_history(repo_root):
        return None
    out = _git_text(
        repo_root, "diff", "-z", "--name-only", "--find-renames", f"{base_ref}...{head_ref}"
    )
    if out is None:
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
