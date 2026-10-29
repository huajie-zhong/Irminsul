"""Tests for `irminsul.git.mtime` against a real git repo in tmp_path."""

from __future__ import annotations

import datetime as _dt
import subprocess
from pathlib import Path
from typing import Any

import pytest

from irminsul.git.mtime import (
    GitTime,
    bulk_last_commit_times,
    has_history,
    last_commit_time_any_repo,
    pending_time,
)
from irminsul.git.reader import GitReader

from .conftest import commit_file, git, git_init, load_graph, write, write_config


def _git_log_last(root: Path, rel_path: str) -> GitTime:
    """`git log -1` for one path: the per-path answer the bulk map must reproduce."""
    out = subprocess.run(
        ["git", "-C", str(root), "log", "-1", "--format=%H %ct", "--", rel_path],
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    sha, _, when = out.partition(" ")
    return GitTime(sha=sha, when=_dt.datetime.fromtimestamp(int(when), tz=_dt.UTC))


def test_no_repo_has_no_history(tmp_path: Path) -> None:
    assert not has_history(GitReader(), tmp_path)


def test_empty_repo_has_no_history(tmp_path: Path) -> None:
    git_init(tmp_path)
    assert not has_history(GitReader(), tmp_path)


def test_last_commit_time_any_repo_finds_history(tmp_path: Path) -> None:
    when = _dt.datetime(2025, 1, 1, 12, tzinfo=_dt.UTC)
    git_init(tmp_path)
    commit_file(tmp_path, "src/foo.py", "x = 1\n", "first", when=when)

    gt = last_commit_time_any_repo(GitReader(), tmp_path / "src" / "foo.py", tmp_path)
    assert gt is not None
    assert gt.when is not None
    assert gt.sha is not None
    assert gt.when.tzinfo is not None
    assert gt.when == when


def test_bulk_last_commit_times_matches_per_file_lookup(tmp_path: Path) -> None:
    git_init(tmp_path)
    commit_file(tmp_path, "src/old.py", "old\n", "old commit", when="1767225600 +0000")
    commit_file(tmp_path, "src/new.py", "new\n", "newer commit", when="1769904000 +0000")
    commit_file(tmp_path, "deep/nested/file.py", "x\n", "third commit", when="1772323200 +0000")

    bulk = bulk_last_commit_times(GitReader(), tmp_path)
    for rel in ("src/old.py", "src/new.py", "deep/nested/file.py"):
        assert bulk[rel] == _git_log_last(tmp_path, rel)
    assert bulk["src/old.py"].when != bulk["src/new.py"].when


def test_bulk_last_commit_times_no_repo_returns_empty(tmp_path: Path) -> None:
    assert bulk_last_commit_times(GitReader(), tmp_path) == {}


def test_bulk_last_commit_times_empty_repo_returns_empty(tmp_path: Path) -> None:
    git_init(tmp_path)
    assert bulk_last_commit_times(GitReader(), tmp_path) == {}


def test_bulk_last_commit_times_is_cached_across_calls(tmp_path: Path) -> None:
    """Same reader and repo root return the identical dict object on a second call --
    proof the map is built once and reused, not recomputed per lookup."""
    git_init(tmp_path)
    commit_file(tmp_path, "src/foo.py", "x = 1\n", "first")

    reader = GitReader()
    first = bulk_last_commit_times(reader, tmp_path)
    second = bulk_last_commit_times(reader, tmp_path)
    assert first is second


def test_bulk_last_commit_times_is_read_again_by_a_new_reader(tmp_path: Path) -> None:
    """The cache belongs to the reader, so a new reader sees history committed after
    an earlier one read it."""
    git_init(tmp_path)
    commit_file(tmp_path, "src/foo.py", "x = 1\n", "first")
    first = bulk_last_commit_times(GitReader(), tmp_path)

    commit_file(tmp_path, "src/bar.py", "y = 2\n", "second")
    second = bulk_last_commit_times(GitReader(), tmp_path)

    assert "src/bar.py" not in first
    assert "src/bar.py" in second


def test_last_commit_time_any_repo_issues_one_subprocess_for_many_lookups(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The whole point of batching: N per-path lookups must not cost N git
    subprocess spawns. `GitReader.run_live` is the single transport point for
    every git subcommand, so counting its calls across many lookups on the
    same repo root pins the O(1)-per-repo behaviour instead of O(1)-per-path."""
    git_init(tmp_path)
    paths = [f"src/file{i}.py" for i in range(20)]
    for rel in paths:
        commit_file(tmp_path, rel, "x = 1\n", f"commit {rel}")

    call_count = 0
    original_run = GitReader.run_live

    def counting_run(self: GitReader, *args: Any, **kwargs: Any) -> Any:
        nonlocal call_count
        call_count += 1
        return original_run(self, *args, **kwargs)

    monkeypatch.setattr(GitReader, "run_live", counting_run)

    reader = GitReader()
    for rel in paths:
        result = last_commit_time_any_repo(reader, tmp_path / rel, tmp_path)
        assert result is not None and result.when is not None

    assert 1 <= call_count <= 3, f"expected O(1) git subprocess calls, saw {call_count}"


def test_bulk_last_commit_times_skips_merge_commits_like_plain_name_only(
    tmp_path: Path,
) -> None:
    """Documented, accepted approximation: a merge commit whose conflict
    resolution is the *only* place a file's content changes is invisible to
    `--name-only` (same as plain `git log` without `-m`), so the bulk map
    resolves to the latest non-merge ancestor instead of the merge itself.
    `git log -1 -- <path>`'s default-simplification answer can differ
    in exactly this case -- pinned here so it reads as intentional, not as a
    regression, if it's ever hit again."""
    git_init(tmp_path)
    commit_file(tmp_path, "file.txt", "a\n", "base")
    default_branch = git(tmp_path, "branch", "--show-current")

    git(tmp_path, "checkout", "-q", "-b", "feature")
    commit_file(tmp_path, "file.txt", "b\n", "feature change")

    git(tmp_path, "checkout", "-q", default_branch)
    main_sha = commit_file(tmp_path, "file.txt", "c\n", "main change")

    try:
        git(tmp_path, "merge", "feature", "--no-ff")
    except AssertionError:
        commit_file(tmp_path, "file.txt", "merged\n", "merge conflict resolution")
    merge_sha = git(tmp_path, "rev-parse", "HEAD")

    ground_truth = _git_log_last(tmp_path, "file.txt")
    bulk = bulk_last_commit_times(GitReader(), tmp_path)["file.txt"]

    assert ground_truth.sha == merge_sha
    assert bulk.sha == main_sha


_DAY = _dt.date(2026, 3, 1)


def _feb(day: int) -> _dt.datetime:
    return _dt.datetime(2026, 2, day, 12, tzinfo=_dt.UTC)


def _repo_with_uncommitted_work(root: Path) -> None:
    git_init(root)
    commit_file(root, ".gitignore", "ignored.txt\n", "ignore", when=_feb(1))
    commit_file(root, "src/clean.py", "c = 1\n", "clean", when=_feb(10))
    commit_file(root, "src/edited.py", "e = 1\n", "edited", when=_feb(20))
    commit_file(root, "src/staged.py", "s = 1\n", "staged", when=_feb(25))
    write(root, "src/edited.py", "e = 2\n")
    write(root, "src/staged.py", "s = 2\n")
    git(root, "add", "src/staged.py")
    write(root, "src/untracked.py", "u = 1\n")
    write(root, "ignored.txt", "nothing\n")


def test_uncommitted_paths_read_as_one_instant_later_than_every_commit(tmp_path: Path) -> None:
    _repo_with_uncommitted_work(tmp_path)
    pending = pending_time(_DAY)

    bulk = bulk_last_commit_times(GitReader(pending=pending), tmp_path)

    assert {bulk[p] for p in ("src/edited.py", "src/staged.py", "src/untracked.py")} == {pending}
    assert "ignored.txt" not in bulk
    assert bulk["src/clean.py"] == _git_log_last(tmp_path, "src/clean.py")
    clean = bulk["src/clean.py"].when
    assert clean is not None and pending.when is not None
    assert clean < pending.when


def test_a_reader_with_no_pending_instant_reads_commits_alone(tmp_path: Path) -> None:
    _repo_with_uncommitted_work(tmp_path)

    bulk = bulk_last_commit_times(GitReader(), tmp_path)

    assert bulk["src/edited.py"] == _git_log_last(tmp_path, "src/edited.py")
    assert "src/untracked.py" not in bulk


def test_the_pending_instant_is_the_end_of_the_given_day() -> None:
    when = pending_time(_DAY).when
    assert when is not None
    assert when.date() == _DAY
    assert when > _dt.datetime(2026, 3, 1, 23, 59, 59, tzinfo=_dt.UTC)
    assert when < _dt.datetime(2026, 3, 2, tzinfo=_dt.UTC)


def test_uncommitted_work_costs_one_status_per_repository(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _repo_with_uncommitted_work(tmp_path)
    statuses = 0
    original_run = GitReader.run_live

    def counting_run(self: GitReader, repo_root: Path, *args: str) -> Any:
        nonlocal statuses
        statuses += args[0] == "status"
        return original_run(self, repo_root, *args)

    monkeypatch.setattr(GitReader, "run_live", counting_run)

    reader = GitReader(pending=pending_time(_DAY))
    for rel in ("src/clean.py", "src/edited.py", "src/untracked.py"):
        last_commit_time_any_repo(reader, tmp_path / rel, tmp_path)

    assert statuses == 1


def test_a_graph_counts_uncommitted_work_unless_asked_for_commits_only(tmp_path: Path) -> None:
    write_config(tmp_path)

    assert load_graph(tmp_path, now=_DAY).git.pending == pending_time(_DAY)
    assert load_graph(tmp_path, now=_DAY, committed_only=True).git.pending is None
