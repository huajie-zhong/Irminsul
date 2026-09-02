"""Git utilities used by soft-deterministic checks (mtime-drift, etc.)."""

from irminsul.git.mtime import (
    GitTime,
    bulk_last_commit_times,
    has_history,
    is_shallow,
    last_commit_time,
    last_commit_time_for_paths,
)

__all__ = [
    "GitTime",
    "bulk_last_commit_times",
    "has_history",
    "is_shallow",
    "last_commit_time",
    "last_commit_time_for_paths",
]
