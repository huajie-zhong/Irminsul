"""Change enumeration over git, shared by every command that judges a change.

One porcelain-parsing routine so every consumer sees the same definition of
"the current local change": staged, unstaged, and untracked files.
`working_tree_changed_paths` and `changed_line_numbers` report them project-relative
even when the config root sits below the git root. `changed_since`, the range from a
merge base to the working tree, is answered only for a project that is its own git
root: below it, it returns None and the local mode falls back to
`working_tree_changed_paths`. `changed_since` is the one answer to which paths changed
since a base ref, so every command that judges a change agrees about them.
"""

from __future__ import annotations

import re
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

from irminsul.errors import UserError
from irminsul.git.mtime import has_history

if TYPE_CHECKING:
    from irminsul.git.reader import GitReader


class GitChangesError(UserError):
    """Raised when git is unavailable or a git call fails."""


@dataclass(frozen=True)
class ChangedPaths:
    """What a change touched, by repo-relative POSIX path."""

    merge_base: str
    """The commit the change is measured from: the merge base of the base ref and `HEAD`."""
    changed: frozenset[str]
    uncommitted: frozenset[str]
    """The changed paths the commits do not hold. Empty when only commits are judged."""


def changed_since(
    git: GitReader, repo_root: Path, base: str, *, committed_only: bool = False
) -> ChangedPaths | None:
    """The paths that differ between the merge base of `base` and `HEAD`, and the working tree.

    Staged and unstaged edits, deletions and untracked files that gitignore does not exclude
    all count, so a clean tree gives exactly `git diff <base>...HEAD`. Renames are followed,
    so a renamed file shows once at its destination, but only once git sees both halves:
    `git mv` stages them, while a file moved by hand reads as a deletion plus a new file.
    With `committed_only` the range ends at `HEAD` and nothing uncommitted is read.

    None when the repo has no usable history, the base cannot be resolved, or the two share
    no history: the caller treats that as "no diff coverage" rather than an error.
    """
    if not has_history(git, repo_root):
        return None
    base_commit = merge_base(git, repo_root, base, "HEAD")
    if base_commit is None:
        return None
    if committed_only:
        committed = git.text(
            repo_root, "diff", "-z", "--name-only", "--find-renames", base_commit, "HEAD"
        )
        if committed is None:
            return None
        return ChangedPaths(base_commit, _nul_names(committed), frozenset())
    tracked = git.text_live(repo_root, "diff", "-z", "--name-only", "--find-renames", base_commit)
    untracked = git.text_live(repo_root, "ls-files", "--others", "--exclude-standard", "-z")
    if tracked is None or untracked is None:
        return None
    try:
        dirty = frozenset(working_tree_changed_paths(git, repo_root))
    except GitChangesError:
        return None
    changed = _nul_names(tracked) | _nul_names(untracked)
    return ChangedPaths(base_commit, changed, dirty & changed)


def _nul_names(output: str) -> frozenset[str]:
    return frozenset(name for name in output.split("\0") if name)


def working_tree_changed_paths(git: GitReader, repo_root: Path) -> list[str]:
    """Sorted project-relative POSIX paths of staged, unstaged, and untracked files."""
    prefix = _git_worktree_prefix(git, repo_root)
    result = _run_git(
        git,
        repo_root,
        "status",
        "--porcelain",
        "-z",
        "--untracked-files=all",
        "--",
        ".",
        live=True,
    )
    if result.returncode != 0:
        raise GitChangesError(_git_error_detail(result, "git status failed"))

    paths: list[str] = []
    records = result.stdout.split("\0")
    index = 0
    while index < len(records):
        record = records[index]
        index += 1
        if not record:
            continue

        status = record[:2]
        path = _project_relative_git_path(record[3:], prefix)
        if not path:
            continue
        paths.append(path)

        if "R" in status or "C" in status:
            index += 1

    return sorted(paths)


# The object id of git's empty tree: the base of a repository with no commits yet.
_EMPTY_TREE = "4b825dc642cb6eb9a060e54bf8d69288fbee4904"
_HUNK_RE = re.compile(r"^@@ -\d+(?:,\d+)? \+(\d+)(?:,(\d+))? @@")


def changed_line_numbers(
    git: GitReader, repo_root: Path, base_ref: str | None = None, *, committed_only: bool = False
) -> dict[str, set[int] | None]:
    """Changed line numbers by project-relative POSIX path.

    Compares the working tree with `base_ref`, or with `HEAD` when none is given, so
    staged and unstaged edits both count. An untracked file maps to None: every line
    is new. With `committed_only` the comparison ends at `HEAD` and untracked files are
    not read.
    """
    prefix = _git_worktree_prefix(git, repo_root)
    if (
        base_ref is None
        and _run_git(git, repo_root, "rev-parse", "--verify", "-q", "HEAD").returncode
    ):
        base_ref = _EMPTY_TREE
    result = _run_git(
        git,
        repo_root,
        "-c",
        "core.quotePath=false",
        "diff",
        "-U0",
        "--no-color",
        "--no-ext-diff",
        base_ref or "HEAD",
        *(["HEAD"] if committed_only else []),
        "--",
        ".",
        live=not committed_only,
    )
    if result.returncode != 0:
        raise GitChangesError(_git_error_detail(result, "git diff failed"))

    changed: dict[str, set[int] | None] = {}
    current: str | None = None
    for line in result.stdout.splitlines():
        if line.startswith("+++ "):
            target = line[4:]
            current = (
                _project_relative_git_path(target[2:], prefix) if target.startswith("b/") else None
            )
            continue
        hunk = _HUNK_RE.match(line)
        if hunk is None or not current:
            continue
        start = int(hunk.group(1))
        count = int(hunk.group(2)) if hunk.group(2) is not None else 1
        lines = changed.setdefault(current, set())
        assert lines is not None
        lines.update(range(start, start + count) if count else {start})

    if committed_only:
        return changed
    untracked = _run_git(
        git, repo_root, "ls-files", "--others", "--exclude-standard", "-z", "--", ".", live=True
    )
    if untracked.returncode != 0:
        raise GitChangesError(_git_error_detail(untracked, "git ls-files failed"))
    for record in untracked.stdout.split("\0"):
        if record:
            changed[record.replace(chr(92), "/")] = None
    return changed


def merge_base(git: GitReader, repo_root: Path, first: str, second: str) -> str | None:
    """The merge base of two refs, or None when they share no history."""
    result = _run_git(git, repo_root, "merge-base", first, second)
    if result.returncode != 0:
        return None
    return result.stdout.strip() or None


def unmerged_branch_commits(git: GitReader, repo_root: Path) -> tuple[str, int] | None:
    """The default branch's remote ref and how many commits `HEAD` holds that it lacks.

    For a command run without a base, which compares the working tree with `HEAD` and so
    cannot see work this branch already committed. The ref is `origin/HEAD`'s target, else
    `origin/main`, else `origin/master`, whichever this checkout has first: a guess at the
    base, offered to the reader and never used as one. None when no such ref exists or the
    branch holds nothing it lacks.
    """
    target = _run_git(git, repo_root, "symbolic-ref", "--short", "-q", "refs/remotes/origin/HEAD")
    named = target.stdout.strip() if target.returncode == 0 else ""
    for ref in dict.fromkeys([*([named] if named else []), "origin/main", "origin/master"]):
        if resolve_ref(git, repo_root, ref) is None:
            continue
        counted = _run_git(git, repo_root, "rev-list", "--count", f"{ref}..HEAD")
        count = int(counted.stdout.strip() or 0) if counted.returncode == 0 else 0
        return (ref, count) if count else None
    return None


def commit_trailers(
    git: GitReader, repo_root: Path, base_ref: str, head_ref: str, key: str
) -> list[tuple[str, str]]:
    """(abbreviated commit, value) for each `key` trailer on the commits `head_ref` adds
    to `base_ref`, oldest commit first.

    Git's own trailer parser reads the message, so a line in the body that only looks
    like a trailer is not one. A range git cannot read yields nothing: a trailer can only
    acknowledge a finding, so reading none leaves every finding standing.
    """
    result = _run_git(
        git,
        repo_root,
        "log",
        "-z",
        "--reverse",
        f"--format=%h%n%(trailers:key={key},valueonly,unfold)",
        f"{base_ref}..{head_ref}",
    )
    if result.returncode != 0:
        return []
    out: list[tuple[str, str]] = []
    for record in result.stdout.split("\0"):
        lines = record.strip().splitlines()
        if not lines:
            continue
        out.extend((lines[0], value.strip()) for value in lines[1:] if value.strip())
    return out


def files_changed_after(
    git: GitReader, repo_root: Path, commit: str, head: str, base: str
) -> frozenset[str] | None:
    """Project-relative paths the range's own commits after `commit` change, or None when
    git cannot say.

    Only commits `head` adds to `base`, other than merges, count. A pull request's checkout
    is a merge commit, and what the base branch gained since the branch was cut is not a
    later change of this one. Renames are off, so a move counts as the old path's deletion
    and the new path's addition, and the old path is among the files that changed.
    """
    prefix = _git_worktree_prefix(git, repo_root)
    result = _run_git(
        git,
        repo_root,
        "-c",
        "core.quotePath=false",
        "log",
        "--no-merges",
        "--no-renames",
        "--format=",
        "--name-only",
        head,
        f"^{commit}",
        f"^{base}",
        "--",
    )
    if result.returncode != 0:
        return None
    return frozenset(
        relative
        for line in result.stdout.splitlines()
        if line and (relative := _project_relative_git_path(line, prefix)) is not None
    )


def head_revision(git: GitReader, repo_root: Path) -> str | None:
    """The commit `HEAD` names in this repository, or None when there is none.

    None covers every way the question has no answer — no repository, no commit yet, git
    absent from PATH — because the callers all treat those the same way: a boundary that
    cannot be established is not one to record.
    """
    result = _run_git(git, repo_root, "rev-parse", "HEAD")
    if result.returncode != 0:
        return None
    return result.stdout.strip() or None


def has_revision(git: GitReader, repo_root: Path, rev: str) -> bool:
    """Whether this repository holds `rev` as a commit.

    `^{commit}` rather than a bare rev-parse: a bare one resolves a branch name, an
    abbreviation, or anything else git is willing to interpret, and the question here is
    whether a specific recorded commit is present in this history. A shallow clone that
    does not reach it answers False, which is the honest answer — the revision is not in
    this checkout, so nothing can be read at it.
    """
    return (
        _run_git(git, repo_root, "rev-parse", "--verify", "--quiet", f"{rev}^{{commit}}").returncode
        == 0
    )


def is_ancestor(git: GitReader, repo_root: Path, candidate: str, of: str) -> bool:
    """Whether `candidate` is contained in the history reachable from `of`.

    False when either is missing from this checkout, which is the honest answer: a commit this
    clone cannot see is a commit it cannot place on a history. Callers that need to tell "not
    an ancestor" from "not here" ask about presence separately.
    """
    return _run_git(git, repo_root, "merge-base", "--is-ancestor", candidate, of).returncode == 0


def resolve_ref(git: GitReader, repo_root: Path, ref: str) -> str | None:
    """The commit a declared source ref names, or None when this checkout has no such ref.

    Exactly one candidate is tried, so there is no precedence order and no way for the wrong
    ref to answer. A value that already starts with `refs/` is used as written; anything else
    is a remote-qualified name and becomes `refs/remotes/<value>`. A bare branch name cannot
    arrive here — the configuration refuses it — because in a checkout that is the *local*
    branch, which anybody can move and nobody sees move, while the boundary has to be a
    statement about the repository's shared history.

    Deliberately not `git rev-parse <ref>`: that would try refs, then tags, then abbreviated
    object ids, and a local branch would shadow the remote one it was named after.
    """
    candidate = ref if ref.startswith("refs/") else f"refs/remotes/{ref}"
    result = _run_git(git, repo_root, "rev-parse", "--verify", "--quiet", f"{candidate}^{{commit}}")
    if result.returncode != 0:
        return None
    return result.stdout.strip() or None


def tracked_paths_at_ref(git: GitReader, repo_root: Path, ref: str) -> set[str] | None:
    """Every project-relative tracked path at `ref`, or None when git cannot read it.

    `exists_at_ref` answers this one path at a time, which is one subprocess per path. A
    first adoption record can name thousands, and the question asked of all of them is the
    same one, so the tree is listed once. None rather than an empty set for an unreadable
    ref: a caller concluding "this path was never here" from a failed read would accuse
    every path in the record at once.
    """
    result = _run_git(
        git,
        repo_root,
        "-c",
        "core.quotePath=false",
        "ls-tree",
        "-r",
        "--name-only",
        "--full-tree",
        ref,
    )
    if result.returncode != 0:
        return None
    prefix = _git_worktree_prefix(git, repo_root)
    return {
        relative
        for line in result.stdout.splitlines()
        if (relative := _project_relative_git_path(line, prefix)) is not None
    }


def files_at_ref(git: GitReader, repo_root: Path, ref: str, directory: str) -> list[str]:
    """Project-relative paths of the files under `directory` at `ref`."""
    paths = tracked_paths_at_ref(git, repo_root, ref)
    if paths is None:
        return []
    base = directory.strip("/") + "/"
    return sorted(path for path in paths if path.startswith(base))


def renamed_paths(
    git: GitReader, repo_root: Path, base_ref: str, head_ref: str | None
) -> dict[str, str]:
    """Old path to new path for every file git reports as renamed between two refs.

    A `head_ref` of None compares the base against the working tree, so a rename staged
    but not yet committed counts. A ref git cannot resolve yields no renames rather than
    raising, because the caller reports removals either way.
    """
    refs = [base_ref] if head_ref is None else [base_ref, head_ref]
    result = _run_git(
        git,
        repo_root,
        "-c",
        "core.quotePath=false",
        "diff",
        "--find-renames",
        "--diff-filter=R",
        "--name-status",
        "-z",
        *refs,
        live=head_ref is None,
    )
    if result.returncode != 0:
        return {}
    prefix = _git_worktree_prefix(git, repo_root)
    fields = result.stdout.split("\0")
    out: dict[str, str] = {}
    for index in range(0, len(fields) - 2, 3):
        status, old, new = fields[index], fields[index + 1], fields[index + 2]
        if not status.startswith("R"):
            break
        old_relative = _project_relative_git_path(old, prefix)
        new_relative = _project_relative_git_path(new, prefix)
        if old_relative is not None and new_relative is not None:
            out[old_relative] = new_relative
    return out


def exists_at_ref(git: GitReader, repo_root: Path, ref: str, path: str) -> bool | None:
    """Whether a project-relative file exists at `ref`, or None when git cannot say.

    `file_at_ref` answers None both for a file that is not there and for a ref it cannot
    read, which is too little to conclude that a file was never there.
    """
    result = _run_git(git, repo_root, "ls-tree", "--name-only", ref, "--", path)
    if result.returncode != 0:
        return None
    return bool(result.stdout.strip())


def file_at_ref(git: GitReader, repo_root: Path, ref: str, path: str) -> str | None:
    """A project-relative file's content at `ref`, or None when it did not exist there."""
    result = _run_git(git, repo_root, "show", f"{ref}:./{path}")
    if result.returncode != 0:
        return None
    return result.stdout


def _git_worktree_prefix(git: GitReader, repo_root: Path) -> str:
    result = _run_git(git, repo_root, "rev-parse", "--show-prefix")
    if result.returncode != 0:
        raise GitChangesError(_git_error_detail(result, "git rev-parse failed"))

    prefix = result.stdout.rstrip("\r\n")
    if prefix and not prefix.endswith("/"):
        prefix = f"{prefix}/"
    return prefix


def _run_git(
    git: GitReader, repo_root: Path, *args: str, live: bool = False
) -> subprocess.CompletedProcess[str]:
    """`git.run`, or `git.run_live` for a question the working tree answers."""
    try:
        return git.run_live(repo_root, *args) if live else git.run(repo_root, *args)
    except FileNotFoundError as exc:
        raise GitChangesError(
            "git command not found; ensure git is installed and in your PATH"
        ) from exc


def _git_error_detail(result: subprocess.CompletedProcess[str], fallback: str) -> str:
    return result.stderr.strip() or result.stdout.strip() or fallback


def _project_relative_git_path(path: str, prefix: str) -> str | None:
    if not prefix:
        return path
    if not path.startswith(prefix):
        return None
    return path[len(prefix) :]
