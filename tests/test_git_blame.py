"""Tests for per-line last-change times."""

from __future__ import annotations

import datetime as _dt
from pathlib import Path

from irminsul.git.blame import LineTimes
from irminsul.git.mtime import pending_time
from irminsul.git.reader import GitReader

from .conftest import commit_file, git_init

OLD = _dt.datetime(2020, 1, 1, tzinfo=_dt.UTC)


def test_range_time_is_the_newest_line_in_the_range(tmp_path: Path) -> None:
    git_init(tmp_path)
    path = tmp_path / "mod.py"
    commit_file(tmp_path, "mod.py", "a = 1\nb = 2\nc = 3\n", "old", when=OLD)
    commit_file(tmp_path, "mod.py", "a = 1\nb = 20\nc = 3\n", "new")

    lines = LineTimes(GitReader())
    assert lines.newest(path, 1, 1) == OLD.timestamp()
    assert lines.newest(path, 3, 3) == OLD.timestamp()
    assert lines.newest(path, 1, 3) > OLD.timestamp()
    assert lines.newest(path) == lines.newest(path, 1, 3)


def test_uncommitted_and_untracked_lines_read_as_new(tmp_path: Path) -> None:
    git_init(tmp_path)
    tracked = tmp_path / "mod.py"
    commit_file(tmp_path, "mod.py", "a = 1\n", "old", when=OLD)
    tracked.write_text("a = 2\n", encoding="utf-8")
    untracked = tmp_path / "new.py"
    untracked.write_text("x = 1\n", encoding="utf-8")

    lines = LineTimes(GitReader())
    assert lines.newest(tracked, 1, 1) > OLD.timestamp()
    assert lines.newest(untracked) > OLD.timestamp()


def test_uncommitted_lines_read_as_the_pending_instant(tmp_path: Path) -> None:
    git_init(tmp_path)
    tracked = tmp_path / "mod.py"
    commit_file(tmp_path, "mod.py", "a = 1\nb = 2\n", "old", when=OLD)
    tracked.write_text("a = 1\nb = 3\n", encoding="utf-8")
    untracked = tmp_path / "new.py"
    untracked.write_text("x = 1\n", encoding="utf-8")
    pending = pending_time(_dt.date(2026, 3, 1))
    assert pending.when is not None

    lines = LineTimes(GitReader(pending=pending))

    assert lines.newest(tracked, 1, 1) == OLD.timestamp()
    assert lines.newest(tracked, 2, 2) == pending.when.timestamp()
    assert lines.newest(untracked) == pending.when.timestamp()


def test_outside_a_repository_has_no_time(tmp_path: Path) -> None:
    path = tmp_path / "loose.py"
    path.write_text("a = 1\n", encoding="utf-8")
    assert LineTimes(GitReader()).newest(path) is None
