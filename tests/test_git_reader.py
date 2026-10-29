"""Tests for `GitReader`, one invocation's questions to git."""

from __future__ import annotations

from pathlib import Path

from irminsul.git.changes import file_at_ref, working_tree_changed_paths
from irminsul.git.mtime import last_commit_time_any_repo
from irminsul.git.reader import GitReader

from .conftest import commit_all, git_init, load_graph, write, write_config


def _repo(tmp_path: Path) -> Path:
    write_config(tmp_path, source_roots=["src"])
    write(tmp_path, "src/a.py", "A = 1\n")
    write(tmp_path, "docs/components/a.md", "---\nid: a\ntitle: A\nstatus: stable\n---\n# A\n")
    git_init(tmp_path)
    commit_all(tmp_path, "first", when="2026-01-01T00:00:00+00:00")
    return tmp_path


def test_a_reader_asks_a_history_question_once(tmp_path: Path) -> None:
    repo = _repo(tmp_path)
    git = GitReader()

    before = file_at_ref(git, repo, "HEAD", "src/a.py")
    write(repo, "src/a.py", "A = 2\n")
    commit_all(repo, "second", when="2026-01-02T00:00:00+00:00")

    assert before == "A = 1\n"
    assert file_at_ref(git, repo, "HEAD", "src/a.py") == before
    assert file_at_ref(GitReader(), repo, "HEAD", "src/a.py") == "A = 2\n"


def test_a_working_tree_question_is_asked_every_time(tmp_path: Path) -> None:
    repo = _repo(tmp_path)
    git = GitReader()

    assert working_tree_changed_paths(git, repo) == []
    write(repo, "src/b.py", "B = 1\n")

    assert working_tree_changed_paths(git, repo) == ["src/b.py"]


def test_building_a_graph_does_not_discard_another_graphs_history(tmp_path: Path) -> None:
    """The base side of `--delta` is a second graph in the same invocation; building it
    used to drop the history the first graph had read."""
    repo = _repo(tmp_path)
    first = load_graph(repo)
    read = last_commit_time_any_repo(first.git, repo / "src" / "a.py", repo)
    write(repo, "src/a.py", "A = 2\n")
    commit_all(repo, "second", when="2026-01-02T00:00:00+00:00")

    second = load_graph(repo)

    assert first.git is not second.git
    assert last_commit_time_any_repo(first.git, repo / "src" / "a.py", repo) == read
    newer = last_commit_time_any_repo(second.git, repo / "src" / "a.py", repo)
    assert read is not None and newer is not None and newer.sha != read.sha
