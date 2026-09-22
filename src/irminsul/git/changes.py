"""Working-tree change enumeration shared by `context --changed` and `change`.

One porcelain-parsing routine so every consumer sees the same definition of
"the current local change": staged, unstaged, and untracked files, project-
relative even when the config root sits below the git root.
"""

from __future__ import annotations

import re
import subprocess
from pathlib import Path


class GitChangesError(Exception):
    """Raised when git is unavailable or a git call fails."""


def working_tree_changed_paths(repo_root: Path) -> list[str]:
    """Sorted project-relative POSIX paths of staged, unstaged, and untracked files."""
    prefix = _git_worktree_prefix(repo_root)
    result = _run_git(
        repo_root,
        "status",
        "--porcelain",
        "-z",
        "--untracked-files=all",
        "--",
        ".",
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
    repo_root: Path, base_ref: str | None = None
) -> dict[str, set[int] | None]:
    """Changed line numbers by project-relative POSIX path.

    Compares the working tree with `base_ref`, or with `HEAD` when none is given, so
    staged and unstaged edits both count. An untracked file maps to None: every line
    is new.
    """
    prefix = _git_worktree_prefix(repo_root)
    if base_ref is None and _run_git(repo_root, "rev-parse", "--verify", "-q", "HEAD").returncode:
        base_ref = _EMPTY_TREE
    result = _run_git(
        repo_root,
        "-c",
        "core.quotePath=false",
        "diff",
        "-U0",
        "--no-color",
        "--no-ext-diff",
        base_ref or "HEAD",
        "--",
        ".",
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

    untracked = _run_git(repo_root, "ls-files", "--others", "--exclude-standard", "-z", "--", ".")
    if untracked.returncode != 0:
        raise GitChangesError(_git_error_detail(untracked, "git ls-files failed"))
    for record in untracked.stdout.split("\0"):
        if record:
            changed[record.replace(chr(92), "/")] = None
    return changed


def merge_base(repo_root: Path, first: str, second: str) -> str | None:
    """The merge base of two refs, or None when they share no history."""
    result = _run_git(repo_root, "merge-base", first, second)
    if result.returncode != 0:
        return None
    return result.stdout.strip() or None


def head_revision(repo_root: Path) -> str | None:
    """The commit `HEAD` names in this repository, or None when there is none.

    None covers every way the question has no answer — no repository, no commit yet, git
    absent from PATH — because the callers all treat those the same way: a boundary that
    cannot be established is not one to record.
    """
    result = _run_git(repo_root, "rev-parse", "HEAD")
    if result.returncode != 0:
        return None
    return result.stdout.strip() or None


def has_revision(repo_root: Path, rev: str) -> bool:
    """Whether this repository holds `rev` as a commit.

    `^{commit}` rather than a bare rev-parse: a bare one resolves a branch name, an
    abbreviation, or anything else git is willing to interpret, and the question here is
    whether a specific recorded commit is present in this history. A shallow clone that
    does not reach it answers False, which is the honest answer — the revision is not in
    this checkout, so nothing can be read at it.
    """
    return (
        _run_git(repo_root, "rev-parse", "--verify", "--quiet", f"{rev}^{{commit}}").returncode == 0
    )


def is_ancestor(repo_root: Path, candidate: str, of: str) -> bool:
    """Whether `candidate` is contained in the history reachable from `of`.

    False when either is missing from this checkout, which is the honest answer: a commit this
    clone cannot see is a commit it cannot place on a history. Callers that need to tell "not
    an ancestor" from "not here" ask about presence separately.
    """
    return _run_git(repo_root, "merge-base", "--is-ancestor", candidate, of).returncode == 0


def resolve_ref(repo_root: Path, ref: str) -> str | None:
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
    result = _run_git(repo_root, "rev-parse", "--verify", "--quiet", f"{candidate}^{{commit}}")
    if result.returncode != 0:
        return None
    return result.stdout.strip() or None


def tracked_paths_at_ref(repo_root: Path, ref: str) -> set[str] | None:
    """Every project-relative tracked path at `ref`, or None when git cannot read it.

    `exists_at_ref` answers this one path at a time, which is one subprocess per path. A
    first adoption record can name thousands, and the question asked of all of them is the
    same one, so the tree is listed once. None rather than an empty set for an unreadable
    ref: a caller concluding "this path was never here" from a failed read would accuse
    every path in the record at once.
    """
    result = _run_git(
        repo_root, "-c", "core.quotePath=false", "ls-tree", "-r", "--name-only", "--full-tree", ref
    )
    if result.returncode != 0:
        return None
    prefix = _git_worktree_prefix(repo_root)
    return {
        relative
        for line in result.stdout.splitlines()
        if (relative := _project_relative_git_path(line, prefix)) is not None
    }


def files_at_ref(repo_root: Path, ref: str, directory: str) -> list[str]:
    """Project-relative paths of the files under `directory` at `ref`."""
    paths = tracked_paths_at_ref(repo_root, ref)
    if paths is None:
        return []
    base = directory.strip("/") + "/"
    return sorted(path for path in paths if path.startswith(base))


def renamed_paths(repo_root: Path, base_ref: str, head_ref: str) -> dict[str, str]:
    """Old path to new path for every file git reports as renamed between two refs.

    `head_ref` of "HEAD" compares the base against the working tree, so a rename staged
    but not yet committed counts. A ref git cannot resolve yields no renames rather than
    raising, because the caller reports removals either way.
    """
    refs = [base_ref] if head_ref == "HEAD" else [base_ref, head_ref]
    result = _run_git(
        repo_root,
        "-c",
        "core.quotePath=false",
        "diff",
        "--find-renames",
        "--diff-filter=R",
        "--name-status",
        "-z",
        *refs,
    )
    if result.returncode != 0:
        return {}
    prefix = _git_worktree_prefix(repo_root)
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


def exists_at_ref(repo_root: Path, ref: str, path: str) -> bool | None:
    """Whether a project-relative file exists at `ref`, or None when git cannot say.

    `file_at_ref` answers None both for a file that is not there and for a ref it cannot
    read, which is too little to conclude that a file was never there.
    """
    result = _run_git(repo_root, "ls-tree", "--name-only", ref, "--", path)
    if result.returncode != 0:
        return None
    return bool(result.stdout.strip())


def file_at_ref(repo_root: Path, ref: str, path: str) -> str | None:
    """A project-relative file's content at `ref`, or None when it did not exist there."""
    result = _run_git(repo_root, "show", f"{ref}:./{path}")
    if result.returncode != 0:
        return None
    return result.stdout


def _git_worktree_prefix(repo_root: Path) -> str:
    result = _run_git(repo_root, "rev-parse", "--show-prefix")
    if result.returncode != 0:
        raise GitChangesError(_git_error_detail(result, "git rev-parse failed"))

    prefix = result.stdout.rstrip("\r\n")
    if prefix and not prefix.endswith("/"):
        prefix = f"{prefix}/"
    return prefix


def _run_git(repo_root: Path, *args: str) -> subprocess.CompletedProcess[str]:
    try:
        return subprocess.run(
            ["git", "-C", str(repo_root), *args],
            check=False,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
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
