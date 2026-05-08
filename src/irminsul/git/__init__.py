"""Git utilities used by soft-deterministic checks (mtime-drift, etc.)."""

from irminsul.git.mtime import (
    GitTime,
    has_history,
    is_shallow,
    last_commit_time,
    last_commit_time_for_paths,
)

__all__ = [
    "GitTime",
    "has_history",
    "is_shallow",
    "last_commit_time",
    "last_commit_time_for_paths",
]
