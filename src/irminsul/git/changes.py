"""Working-tree change enumeration shared by `context --changed` and `change`.

One porcelain-parsing routine so every consumer sees the same definition of
"the current local change": staged, unstaged, and untracked files, project-
relative even when the config root sits below the git root.
"""

from __future__ import annotations

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
