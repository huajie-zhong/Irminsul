"""`changed_since`: what differs between the merge base of a ref and `HEAD`, and the working tree."""

from __future__ import annotations

from pathlib import Path

from irminsul.git.changes import changed_since
from irminsul.git.reader import GitReader

from .conftest import commit_all, commit_file, git, git_init, write

_DAY = "2026-01-{day:02d}T12:00:00"


def _at(day: int) -> str:
    return _DAY.format(day=day)


def _seed(root: Path) -> str:
    git_init(root, branch="main")
    write(root, "a.py", "a = 1\n")
    write(root, "b.py", "b = 1\n")
    write(root, "docs/notes.md", "# notes\n")
    return commit_all(root, "base", when=_at(1))


def _since(root: Path, base: str, *, committed_only: bool = False):
    return changed_since(GitReader(), root, base, committed_only=committed_only)


def _three_dot(root: Path, base: str) -> set[str]:
    """What git itself says `<base>...HEAD` changed, for a tree with nothing uncommitted."""
    return set(git(root, "diff", "--name-only", "--find-renames", f"{base}...HEAD").splitlines())


def test_a_clean_tree_gives_the_three_dot_range(tmp_path: Path) -> None:
    root = tmp_path / "r"
    base = _seed(root)
    git(root, "checkout", "-q", "-b", "feature")
    commit_file(root, "a.py", "a = 2\n", "edit", when=_at(2))
    commit_file(root, "c.py", "c = 1\n", "add", when=_at(3))
    git(root, "rm", "-q", "b.py")
    commit_all(root, "delete", when=_at(4))
    git(root, "mv", "docs/notes.md", "docs/renamed.md")
    commit_all(root, "rename", when=_at(5))

    since = _since(root, base)

    assert since is not None
    assert since.changed == _three_dot(root, base)
    assert since.changed == {"a.py", "b.py", "c.py", "docs/renamed.md"}
    assert since.uncommitted == frozenset()
    assert since.merge_base == base


def test_the_base_branch_moving_on_is_not_part_of_the_change(tmp_path: Path) -> None:
    root = tmp_path / "r"
    base = _seed(root)
    git(root, "checkout", "-q", "-b", "feature")
    commit_file(root, "a.py", "a = 2\n", "feature work", when=_at(2))
    git(root, "checkout", "-q", "main")
    commit_file(root, "b.py", "b = 2\n", "someone else's work", when=_at(3))
    git(root, "checkout", "-q", "feature")

    since = _since(root, "main")

    assert since is not None
    assert since.merge_base == base
    assert since.changed == {"a.py"}
    assert since.changed == _three_dot(root, "main")


def test_a_detached_merge_commit_checkout_gives_the_same_range(tmp_path: Path) -> None:
    """`pull_request` events check out a merge of the branch into the base's tip."""
    root = tmp_path / "r"
    _seed(root)
    git(root, "checkout", "-q", "-b", "feature")
    commit_file(root, "a.py", "a = 2\n", "feature work", when=_at(2))
    git(root, "checkout", "-q", "main")
    commit_file(root, "b.py", "b = 2\n", "base moves on", when=_at(3))
    git(root, "checkout", "-q", "--detach", "main")
    git(root, "merge", "-q", "--no-ff", "-m", "merge the pull request", "feature", when=_at(4))

    since = _since(root, "main")

    assert since is not None
    assert since.changed == {"a.py"}
    assert since.changed == _three_dot(root, "main")
    assert since.uncommitted == frozenset()


def test_staged_unstaged_deleted_and_untracked_work_all_count(tmp_path: Path) -> None:
    root = tmp_path / "r"
    base = _seed(root)
    git(root, "checkout", "-q", "-b", "feature")
    commit_file(root, "a.py", "a = 2\n", "committed", when=_at(2))
    write(root, "a.py", "a = 3\n")
    write(root, "staged.py", "s = 1\n")
    git(root, "add", "staged.py")
    (root / "b.py").unlink()
    write(root, "untracked.py", "u = 1\n")

    since = _since(root, base)

    assert since is not None
    assert since.changed == {"a.py", "b.py", "staged.py", "untracked.py"}
    assert since.uncommitted == {"a.py", "b.py", "staged.py", "untracked.py"}


def test_only_the_paths_no_commit_holds_are_uncommitted(tmp_path: Path) -> None:
    root = tmp_path / "r"
    base = _seed(root)
    git(root, "checkout", "-q", "-b", "feature")
    commit_file(root, "a.py", "a = 2\n", "committed", when=_at(2))
    write(root, "b.py", "b = 2\n")

    since = _since(root, base)

    assert since is not None
    assert since.changed == {"a.py", "b.py"}
    assert since.uncommitted == {"b.py"}


def test_an_ignored_untracked_file_is_excluded_and_a_plain_one_is_not(tmp_path: Path) -> None:
    root = tmp_path / "r"
    git_init(root, branch="main")
    write(root, ".gitignore", "*.log\n")
    write(root, "a.py", "a = 1\n")
    base = commit_all(root, "base", when=_at(1))
    write(root, "build.log", "noise\n")
    write(root, "notes.txt", "kept\n")

    since = _since(root, base)

    assert since is not None
    assert since.changed == {"notes.txt"}


def test_a_staged_rename_is_listed_once_and_a_hand_move_twice(tmp_path: Path) -> None:
    root = tmp_path / "r"
    base = _seed(root)
    git(root, "mv", "a.py", "moved.py")

    staged = _since(root, base)

    assert staged is not None
    assert staged.changed == {"moved.py"}

    git(root, "reset", "-q")
    by_hand = _since(root, base)

    assert by_hand is not None
    assert by_hand.changed == {"a.py", "moved.py"}


def test_committed_only_leaves_the_working_tree_out(tmp_path: Path) -> None:
    root = tmp_path / "r"
    base = _seed(root)
    git(root, "checkout", "-q", "-b", "feature")
    commit_file(root, "a.py", "a = 2\n", "committed", when=_at(2))
    write(root, "b.py", "b = 2\n")
    write(root, "untracked.py", "u = 1\n")

    since = _since(root, base, committed_only=True)

    assert since is not None
    assert since.changed == {"a.py"}
    assert since.uncommitted == frozenset()


def test_a_ref_git_cannot_resolve_or_a_missing_history_reads_as_none(tmp_path: Path) -> None:
    root = tmp_path / "r"
    _seed(root)

    assert _since(root, "no-such-ref") is None
    assert _since(tmp_path / "elsewhere", "main") is None
