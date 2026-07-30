"""Tests for `irminsul.git.mtime` against a real git repo in tmp_path."""

from __future__ import annotations

import datetime as _dt
import subprocess
from pathlib import Path

import pytest
from git import Repo
from git.cmd import Git

from irminsul.git.mtime import (
    GitTime,
    bulk_last_commit_times,
    has_history,
    is_shallow,
    last_commit_time,
    last_commit_time_any_repo,
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


def test_bulk_last_commit_times_matches_per_file_lookup(tmp_path: Path) -> None:
    repo = _init_repo(tmp_path)
    _commit(repo, "src/old.py", "old\n", "old commit")

    import time

    time.sleep(1.1)
    _commit(repo, "src/new.py", "new\n", "newer commit")
    _commit(repo, "deep/nested/file.py", "x\n", "third commit")

    bulk = bulk_last_commit_times(tmp_path)
    assert bulk["src/old.py"] == last_commit_time(tmp_path, Path("src/old.py"))
    assert bulk["src/new.py"] == last_commit_time(tmp_path, Path("src/new.py"))
    assert bulk["deep/nested/file.py"] == last_commit_time(tmp_path, Path("deep/nested/file.py"))


def test_bulk_last_commit_times_no_repo_returns_empty(tmp_path: Path) -> None:
    assert bulk_last_commit_times(tmp_path) == {}


def test_bulk_last_commit_times_empty_repo_returns_empty(tmp_path: Path) -> None:
    _init_repo(tmp_path)
    assert bulk_last_commit_times(tmp_path) == {}


def test_bulk_last_commit_times_is_cached_across_calls(tmp_path: Path) -> None:
    """Same repo root returns the identical dict object on a second call --
    proof the map is built once and reused, not recomputed per lookup."""
    repo = _init_repo(tmp_path)
    _commit(repo, "src/foo.py", "x = 1\n", "first")

    first = bulk_last_commit_times(tmp_path)
    second = bulk_last_commit_times(tmp_path)
    assert first is second


def test_last_commit_time_any_repo_issues_one_subprocess_for_many_lookups(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The whole point of batching: N per-path lookups must not cost N git
    subprocess spawns. `Git.execute` is gitpython's single transport point for
    every git subcommand, so counting its calls across many lookups on the
    same repo root pins the O(1)-per-repo behaviour instead of O(1)-per-path."""
    repo = _init_repo(tmp_path)
    paths = [f"src/file{i}.py" for i in range(20)]
    for rel in paths:
        _commit(repo, rel, "x = 1\n", f"commit {rel}")

    call_count = 0
    original_execute = Git.execute

    def counting_execute(self: Git, *args: object, **kwargs: object) -> object:
        nonlocal call_count
        call_count += 1
        return original_execute(self, *args, **kwargs)  # type: ignore[arg-type]

    monkeypatch.setattr(Git, "execute", counting_execute)

    for rel in paths:
        result = last_commit_time_any_repo(tmp_path / rel, tmp_path)
        assert result is not None and result.when is not None

    assert call_count <= 3, f"expected O(1) git subprocess calls, saw {call_count}"


def test_bulk_last_commit_times_skips_merge_commits_like_plain_name_only(
    tmp_path: Path,
) -> None:
    """Documented, accepted approximation: a merge commit whose conflict
    resolution is the *only* place a file's content changes is invisible to
    `--name-only` (same as plain `git log` without `-m`), so the bulk map
    resolves to the latest non-merge ancestor instead of the merge itself.
    `last_commit_time`'s single-path default-simplification answer can differ
    in exactly this case -- pinned here so it reads as intentional, not as a
    regression, if it's ever hit again."""
    repo = _init_repo(tmp_path)
    fp = tmp_path / "file.txt"
    fp.write_text("a\n", encoding="utf-8")
    repo.index.add(["file.txt"])
    repo.index.commit("base")
    default_branch = repo.active_branch.name

    repo.git.checkout("-b", "feature")
    fp.write_text("b\n", encoding="utf-8")
    repo.index.add(["file.txt"])
    repo.index.commit("feature change")

    repo.git.checkout(default_branch)
    fp.write_text("c\n", encoding="utf-8")
    repo.index.add(["file.txt"])
    repo.index.commit("main change")
    main_sha = repo.head.commit.hexsha

    try:
        repo.git.merge("feature", "--no-ff")
    except Exception:
        fp.write_text("merged\n", encoding="utf-8")
        repo.git.add("file.txt")
        repo.git.commit("-m", "merge conflict resolution")
    merge_sha = repo.head.commit.hexsha
    repo.close()

    ground_truth = last_commit_time(tmp_path, Path("file.txt"))
    bulk = bulk_last_commit_times(tmp_path)["file.txt"]

    assert ground_truth.sha == merge_sha
    assert bulk.sha == main_sha
