"""Tests for `irminsul.git.mtime` against a real git repo in tmp_path."""

from __future__ import annotations

import datetime as _dt
import subprocess
from pathlib import Path

import pytest
from git import Repo

from irminsul.git.mtime import (
    GitTime,
    has_history,
    is_shallow,
    last_commit_time,
    last_commit_time_for_paths,
)


def _init_repo(root: Path) -> Repo:
    repo = Repo.init(root)
    with repo.config_writer() as cw:
        cw.set_value("user", "name", "Test")
        cw.set_value("user", "email", "test@example.com")
    return repo


def _commit(repo: Repo, rel_path: str, content: str, message: str) -> None:
    fp = Path(repo.working_dir) / rel_path
    fp.parent.mkdir(parents=True, exist_ok=True)
    fp.write_text(content, encoding="utf-8")
    repo.index.add([rel_path])
    repo.index.commit(message)


def test_no_repo_returns_no_time(tmp_path: Path) -> None:
    assert last_commit_time(tmp_path, Path("nonexistent")) == GitTime(None, None)
    assert not has_history(tmp_path)


def test_empty_repo_returns_no_time(tmp_path: Path) -> None:
    _init_repo(tmp_path)
    assert last_commit_time(tmp_path, Path("anything")) == GitTime(None, None)
    assert not has_history(tmp_path)


def test_last_commit_time_finds_history(tmp_path: Path) -> None:
    repo = _init_repo(tmp_path)
    _commit(repo, "src/foo.py", "x = 1\n", "first")

    gt = last_commit_time(tmp_path, Path("src/foo.py"))
    assert gt.when is not None
    assert gt.sha is not None
    assert gt.when.tzinfo is not None
    # Within 60s of now (UTC).
    now = _dt.datetime.now(_dt.UTC)
    assert (now - gt.when).total_seconds() < 60


def test_last_commit_time_for_paths_picks_latest(tmp_path: Path) -> None:
    repo = _init_repo(tmp_path)
    _commit(repo, "src/old.py", "old\n", "old commit")

    # Backdate the old commit by amending committer-date via plumbing.
    # Simpler: just commit a second file later — natural ordering works.
    import time

    time.sleep(1.1)
    _commit(repo, "src/new.py", "new\n", "newer commit")

    gt_old = last_commit_time(tmp_path, Path("src/old.py"))
    gt_new = last_commit_time(tmp_path, Path("src/new.py"))
    assert gt_old.when is not None and gt_new.when is not None
    assert gt_new.when >= gt_old.when

    combined = last_commit_time_for_paths(tmp_path, [Path("src/old.py"), Path("src/new.py")])
    assert combined.when is not None
    assert combined.when == gt_new.when


def test_last_commit_time_for_paths_handles_uncommitted(tmp_path: Path) -> None:
    repo = _init_repo(tmp_path)
    _commit(repo, "src/foo.py", "x = 1\n", "first")
    gt = last_commit_time_for_paths(tmp_path, [Path("src/foo.py"), Path("src/never_committed.py")])
    assert gt.when is not None  # still resolves via foo.py


def test_is_shallow_false_for_full_clone(tmp_path: Path) -> None:
    repo = _init_repo(tmp_path)
    _commit(repo, "src/foo.py", "x\n", "first")
    assert not is_shallow(tmp_path)


def test_absolute_path_outside_repo_returns_no_time(tmp_path: Path) -> None:
    repo = _init_repo(tmp_path)
    _commit(repo, "src/foo.py", "x\n", "first")
    other_root = tmp_path.parent
    # An absolute path that can't be made relative to repo_root must not crash.
    assert last_commit_time(tmp_path, other_root.resolve() / "elsewhere") == GitTime(None, None)


@pytest.mark.skipif(
    subprocess.run(["git", "--version"], capture_output=True).returncode != 0,
    reason="git CLI not available",
)
def test_iter_commits_via_relative_path_string(tmp_path: Path) -> None:
    """Sanity check that gitpython accepts a posix-style relative path."""
    repo = _init_repo(tmp_path)
    _commit(repo, "deep/nested/file.py", "x\n", "first")
    gt = last_commit_time(tmp_path, Path("deep/nested/file.py"))
    assert gt.when is not None
