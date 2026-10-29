"""One invocation's questions to git, each asked of git at most once.

A `DocGraph` owns one, `graph.git`, so every check in a run reads the same history and no
answer outlives the graph that asked for it: the next graph — the next command, or the
next call to a long-running MCP server — asks again. A command with no graph makes its own.
"""

from __future__ import annotations

import os
import subprocess
from collections.abc import Callable, Hashable
from pathlib import Path
from typing import TYPE_CHECKING, cast

if TYPE_CHECKING:
    from irminsul.git.mtime import GitTime


class GitReader:
    """Runs git, keeping the answers that cannot change while one invocation runs.

    `run` and `text` keep what they read, keyed by the repository and the arguments: what a
    commit, a ref or the history holds, and where a directory sits in its repository, are
    fixed for the life of an invocation. `run_live` and `text_live` keep nothing, for the
    questions whose answer is the working tree — its status, a diff against it, its untracked
    files — which change when a file is written.

    A ref name such as `HEAD` is assumed not to move during an invocation, because nothing
    in Irminsul commits in-process; code that commits must use a new graph or `run_live`.

    Plain `subprocess` rather than GitPython: GitPython keeps the process it spawned alive
    behind the returned string, and on Windows those handles outlive the call — enough for
    Python 3.13's unraisable hook to surface "subprocess is still running" as a
    `ResourceWarning`, which this project's `filterwarnings = ["error"]` turns into a failure.
    """

    def __init__(self, pending: GitTime | None = None) -> None:
        self.pending = pending
        """The instant a path with uncommitted changes reads as last changed, for every
        reader of history; None reads commits alone."""
        self._runs: dict[tuple[str, tuple[str, ...]], subprocess.CompletedProcess[str]] = {}
        self._derived: dict[Hashable, object] = {}

    def run(self, repo_root: Path, *args: str) -> subprocess.CompletedProcess[str]:
        """`git -C repo_root args`, asked once; raises `OSError` when git cannot start."""
        key = (os.fspath(repo_root), args)
        if key not in self._runs:
            self._runs[key] = self.run_live(repo_root, *args)
        return self._runs[key]

    def run_live(self, repo_root: Path, *args: str) -> subprocess.CompletedProcess[str]:
        """`git -C repo_root args`, asked every time."""
        return subprocess.run(
            ["git", "-C", str(repo_root), *args],
            check=False,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
        )

    def text(self, repo_root: Path, *args: str) -> str | None:
        """Stdout of `run`, or None when the command fails or git is absent."""
        try:
            result = self.run(repo_root, *args)
        except OSError:
            return None
        return result.stdout if result.returncode == 0 else None

    def text_live(self, repo_root: Path, *args: str) -> str | None:
        """Stdout of `run_live`, or None when the command fails or git is absent."""
        try:
            result = self.run_live(repo_root, *args)
        except OSError:
            return None
        return result.stdout if result.returncode == 0 else None

    def remember[T](self, key: Hashable, derive: Callable[[], T]) -> T:
        """What `derive` answers, derived once per key: for a result parsed from git output
        that many callers read, such as every path's last commit at once."""
        if key not in self._derived:
            self._derived[key] = derive()
        return cast(T, self._derived[key])
