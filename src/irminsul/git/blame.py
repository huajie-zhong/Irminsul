"""Per-line last-change times from `git blame`, for range-level freshness."""

from __future__ import annotations

import re
import time
from pathlib import Path

from irminsul.git.mtime import git_root_for
from irminsul.git.reader import GitReader

_HEADER_RE = re.compile(r"^([0-9a-f]{40,64}) \d+ \d+")


class LineTimes:
    """Caches one blame per file; a line with no committed history reads as the reader's
    pending instant, or as now when it has none.

    Blame is asked of the working tree every time, through `run_live`, because an
    uncommitted line is part of the answer.
    """

    def __init__(self, git: GitReader) -> None:
        self._git = git
        self._cache: dict[Path, list[float] | None] = {}

    def newest(self, path: Path, start: int | None = None, end: int | None = None) -> float | None:
        times = self._times(path)
        if times is None:
            return None
        if not times:
            return _uncommitted_time(self._git)
        lo = 1 if start is None else max(1, start)
        hi = len(times) if end is None else min(len(times), end)
        window = times[lo - 1 : hi]
        return max(window) if window else None

    def _times(self, path: Path) -> list[float] | None:
        resolved = path.resolve()
        if resolved not in self._cache:
            self._cache[resolved] = _blame(self._git, resolved)
        return self._cache[resolved]


def _uncommitted_time(git: GitReader) -> float:
    pending = git.pending
    if pending is None or pending.when is None:
        return time.time()
    return pending.when.timestamp()


def _blame(git: GitReader, path: Path) -> list[float] | None:
    root = git_root_for(path)
    if root is None or not path.is_file():
        return None
    try:
        result = git.run_live(root, "blame", "--line-porcelain", "--", str(path))
    except OSError:
        return None
    if result.returncode != 0:
        # Untracked: nothing of it is committed yet.
        return []
    times: list[float] = []
    current = time.time()
    uncommitted = False
    for line in result.stdout.splitlines():
        header = _HEADER_RE.match(line)
        if header is not None:
            uncommitted = set(header.group(1)) == {"0"}
        elif line.startswith("committer-time "):
            current = float(line.split(" ", 1)[1])
        elif line.startswith("\t"):
            times.append(
                _uncommitted_time(git) if uncommitted and git.pending is not None else current
            )
    return times
