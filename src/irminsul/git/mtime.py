"""Last-commit-time helpers for source files.

Checks and reports that ask when a file last changed use these. The
contract is intentionally narrow: functions over `Path`s that ask git through a
`GitReader` and return `GitTime` values that tell the caller "no history
available" via a None payload rather than raising. Callers degrade gracefully (warning
or skip) instead of erroring on tarball checkouts or shallow clones.
"""

from __future__ import annotations

import datetime as _dt
import os
import re
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from irminsul.git.reader import GitReader


@dataclass(frozen=True)
class GitTime:
    sha: str | None
    when: _dt.datetime | None  # UTC; None when no history is available


_NO_TIME = GitTime(sha=None, when=None)


def pending_time(now: _dt.date | None = None) -> GitTime:
    """The one instant a path with uncommitted changes reads as last changed.

    The end of `now`'s day, or of today in UTC: later than every commit made by then, and
    equal to itself, so a doc and the file it cites that were both edited since the last
    commit compare as changed together and neither is after the other.
    """
    day = now if now is not None else _dt.datetime.now(_dt.UTC).date()
    return GitTime(sha=None, when=_dt.datetime.combine(day, _dt.time.max, tzinfo=_dt.UTC))


def has_history(git: GitReader, repo_root: Path) -> bool:
    return history_state(git, repo_root)[0]


def history_state(git: GitReader, repo_root: Path) -> tuple[bool, bool]:
    """(has history, is shallow) — whether this checkout can answer git questions.

    One `git rev-parse` rather than two repository opens, because every `irminsul check`
    asks this.
    """
    stdout = git.text(
        repo_root,
        "rev-parse",
        # `--git-common-dir`, not `--git-dir`: inside a linked worktree the latter is
        # `<main>/.git/worktrees/<name>`, which never holds the `shallow` marker, so a
        # worktree of a shallow clone would report full history. `pristine_checkout` builds
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


def git_root_for(path: Path) -> Path | None:
    """Walk up from path to find a directory containing a .git entry.

    The walk is over the resolved path, so `docs/../code/x` looks in `code` and not in
    `docs`; the root it returns is spelled resolved too.
    """
    path = path.resolve()
    cur = path if path.is_dir() else path.parent
    for candidate in (cur, *cur.parents):
        if (candidate / ".git").exists():
            return candidate
    return None


_LOG_HEADER_RE = re.compile(r"^([0-9a-f]{40,64}) (\d+)$")


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


def bulk_last_commit_times(git: GitReader, repo_root: Path) -> dict[str, GitTime]:
    """One `git log` pass over `repo_root`: repo-relative POSIX path -> its
    latest GitTime, one subprocess for the whole repo rather than one per path.

    Walking newest-first, the first commit that lists a path is that path's
    most recent touch — matching `git log -1 -- <path>` for ordinary commits.
    Merge commits carry no file list under plain `--name-only` (same as everyday
    `git log`), so a path whose only recent change came from a merge's own
    conflict resolution resolves to its latest non-merge ancestor instead — an
    accepted tradeoff for the O(1)-subprocess win.

    When the reader has a pending instant, every path `git status` lists — staged,
    unstaged, and untracked but not ignored — reads as that instant instead of its commit,
    at the cost of one more git call per repository.

    Kept per repo root for the life of `git`. Asking git whether HEAD moved on each
    lookup would cost a subprocess per path, far more than the one `git log` it guards,
    so the answer is bounded by the reader instead: a graph's reader is the graph's, so
    one invocation reads history once and the next invocation — including the next call
    to a long-running MCP server — reads it again.
    """

    def read() -> dict[str, GitTime]:
        raw = git.text_live(repo_root, "log", "--name-only", "-z", "--format=%H %ct")
        if raw is None or not has_history(git, repo_root):
            return {}
        times = _parse_bulk_log(raw)
        if git.pending is not None:
            # Imported here: `changes` reads `has_history` from this module.
            from irminsul.git.changes import GitChangesError, working_tree_changed_paths

            try:
                uncommitted = working_tree_changed_paths(git, repo_root)
            except GitChangesError:
                uncommitted = []
            for path in uncommitted:
                times[path] = git.pending
        return times

    return git.remember(("last-commit-times", os.fspath(repo_root.resolve())), read)


def _bulk_lookup(git: GitReader, repo_root: Path, path: Path) -> GitTime:
    rel = path
    if path.is_absolute():
        try:
            rel = path.relative_to(repo_root)
        except ValueError:
            try:
                rel = path.resolve().relative_to(repo_root.resolve())
            except ValueError:
                return _NO_TIME
    key = PurePosixPath(*rel.parts).as_posix()
    return bulk_last_commit_times(git, repo_root).get(key, _NO_TIME)


def last_commit_time_any_repo(git: GitReader, path: Path, docs_root: Path) -> GitTime | None:
    """The last commit that touched `path`, which may sit in another repository.

    Returns None when path is outside docs_root and no .git is found — caller
    should emit an error Finding. Returns _NO_TIME when git exists but path has
    no commits (same as same-repo behaviour).

    `docs_root` here is the directory irminsul was invoked from — the one that
    owns `irminsul.toml` — which is not necessarily a repository root. The
    common case that needs the lookup at the path's nearest root rather than at
    `docs_root` is a monorepo subfolder:
    irminsul runs from `packages/proj/`, the `.git` sits above at the monorepo
    root, and `git_root_for` walks *up* to find it. The enclosing root is then
    an **ancestor** of `docs_root`, not a descendant, and it is the only repo
    that has any history for the path — asking `docs_root` instead returns
    GitTime(None, None) and every git time silently disappears. Irminsul's own
    fixture repos take this path, since they live inside this git repo.

    The same lookup also covers a repository *below* `docs_root` (a submodule or
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
        return _bulk_lookup(git, root, path)

    nested_root = git_root_for(path)
    if (
        nested_root is None
        or nested_root == docs_root
        or nested_root.resolve() == docs_root.resolve()
    ):
        return _bulk_lookup(git, docs_root, path)
    return _bulk_lookup(git, nested_root, path)
