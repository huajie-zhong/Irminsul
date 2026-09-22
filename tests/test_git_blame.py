"""Tests for per-line last-change times."""

from __future__ import annotations

import datetime as _dt
from pathlib import Path

from git import Repo

from irminsul.git.blame import LineTimes

OLD = _dt.datetime(2020, 1, 1, tzinfo=_dt.UTC)


def _repo(root: Path) -> Repo:
    repo = Repo.init(root)
    with repo.config_writer() as cw:
        cw.set_value("user", "name", "Test")
        cw.set_value("user", "email", "test@example.com")
    return repo


def test_range_time_is_the_newest_line_in_the_range(tmp_path: Path) -> None:
    repo = _repo(tmp_path)
    path = tmp_path / "mod.py"
    path.write_text("a = 1\nb = 2\nc = 3\n", encoding="utf-8")
    repo.index.add(["mod.py"])
    repo.index.commit("old", author_date=OLD, commit_date=OLD)
    path.write_text("a = 1\nb = 20\nc = 3\n", encoding="utf-8")
    repo.index.add(["mod.py"])
    repo.index.commit("new")
    repo.close()

    lines = LineTimes()
    assert lines.newest(path, 1, 1) == OLD.timestamp()
    assert lines.newest(path, 3, 3) == OLD.timestamp()
    assert lines.newest(path, 1, 3) > OLD.timestamp()
    assert lines.newest(path) == lines.newest(path, 1, 3)


def test_uncommitted_and_untracked_lines_read_as_new(tmp_path: Path) -> None:
    repo = _repo(tmp_path)
    tracked = tmp_path / "mod.py"
    tracked.write_text("a = 1\n", encoding="utf-8")
    repo.index.add(["mod.py"])
    repo.index.commit("old", author_date=OLD, commit_date=OLD)
    repo.close()
    tracked.write_text("a = 2\n", encoding="utf-8")
    untracked = tmp_path / "new.py"
    untracked.write_text("x = 1\n", encoding="utf-8")

    lines = LineTimes()
    assert lines.newest(tracked, 1, 1) > OLD.timestamp()
    assert lines.newest(untracked) > OLD.timestamp()


def test_outside_a_repository_has_no_time(tmp_path: Path) -> None:
    path = tmp_path / "loose.py"
    path.write_text("a = 1\n", encoding="utf-8")
    assert LineTimes().newest(path) is None
