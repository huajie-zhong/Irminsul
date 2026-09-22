"""Per-line last-change times from `git blame`, for range-level freshness."""

from __future__ import annotations

import subprocess
import time
from pathlib import Path

from irminsul.git.mtime import git_root_for


class LineTimes:
    """Caches one blame per file; a line with no committed history reads as now."""

    def __init__(self) -> None:
        self._cache: dict[Path, list[float] | None] = {}

    def newest(self, path: Path, start: int | None = None, end: int | None = None) -> float | None:
        times = self._times(path)
        if times is None:
            return None
        if not times:
            return time.time()
        lo = 1 if start is None else max(1, start)
        hi = len(times) if end is None else min(len(times), end)
        window = times[lo - 1 : hi]
        return max(window) if window else None

    def _times(self, path: Path) -> list[float] | None:
        resolved = path.resolve()
        if resolved not in self._cache:
            self._cache[resolved] = _blame(resolved)
        return self._cache[resolved]


def _blame(path: Path) -> list[float] | None:
    root = git_root_for(path)
    if root is None or not path.is_file():
        return None
    try:
        result = subprocess.run(
            ["git", "blame", "--line-porcelain", "--", str(path)],
            cwd=root,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            check=False,
        )
    except OSError:
        return None
    if result.returncode != 0:
        # Untracked: nothing of it is committed yet.
        return []
    times: list[float] = []
    current = time.time()
    for line in result.stdout.splitlines():
        if line.startswith("committer-time "):
            current = float(line.split(" ", 1)[1])
        elif line.startswith("\t"):
            times.append(current)
    return times
