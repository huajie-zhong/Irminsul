"""Unit tests for `irminsul.delta`: fingerprint reuse and the scratch worktree."""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path

import pytest
from git import Repo

from irminsul.checks.base import Finding, Severity
from irminsul.config import IrminsulConfig, Paths
from irminsul.delta import (
    DeltaError,
    compute_delta,
    cross_repo_trees,
    pristine_checkout,
    verify_single_repo_topology,
)


def _finding(
    message: str = "missing frontmatter",
    path: str = "docs/a.md",
    severity: Severity = Severity.error,
) -> Finding:
    return Finding(check="frontmatter", severity=severity, message=message, path=Path(path))


def test_compute_delta_filters_matching_fingerprints() -> None:
    shared = _finding()
    new = _finding(path="docs/b.md")
    result = compute_delta([shared, new], [shared])
    assert result.new == [new]
    assert result.pre_existing == 1


def test_compute_delta_is_line_insensitive() -> None:
    base = replace(_finding(), line=3)
    moved = replace(base, line=42)
    result = compute_delta([moved], [base])
    assert result.new == []
    assert result.pre_existing == 1


def test_compute_delta_changed_message_counts_as_new() -> None:
    base = _finding(message="missing 'audience'")
    changed = _finding(message="missing 'tier'")
    result = compute_delta([changed], [base])
    assert result.new == [changed]
    assert result.pre_existing == 0


def test_compute_delta_does_not_special_case_info() -> None:
    info = _finding(severity=Severity.info)
    result = compute_delta([info], [])
    assert result.new == [info]
    assert result.pre_existing == 0


def _init_repo(root: Path) -> Repo:
    repo = Repo.init(root)
    with repo.config_writer() as cw:
        cw.set_value("user", "name", "Test")
        cw.set_value("user", "email", "test@example.com")
    (root / "a.txt").write_text("1\n", encoding="utf-8")
    repo.index.add(["a.txt"])
    repo.index.commit("seed")
    return repo


def test_pristine_checkout_yields_base_rev_contents(tmp_path: Path) -> None:
    repo = _init_repo(tmp_path)
    base_sha = repo.head.commit.hexsha
    (tmp_path / "a.txt").write_text("2\n", encoding="utf-8")

    with pristine_checkout(tmp_path, base_sha) as base_root:
        assert (base_root / "a.txt").read_text(encoding="utf-8") == "1\n"
        assert base_root != tmp_path

        # The outer handle is closed before the yield, so assert what the caller
        # actually depends on: the scratch tree is still a working linked
        # worktree parked on the base rev, not just a pile of files.
        linked_repo = Repo(base_root)
        try:
            assert linked_repo.head.commit.hexsha == base_sha
        finally:
            linked_repo.close()

    # The caller's working tree is never touched.
    assert (tmp_path / "a.txt").read_text(encoding="utf-8") == "2\n"


def test_pristine_checkout_lives_outside_repo_root(tmp_path: Path) -> None:
    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    _init_repo(repo_root)

    with pristine_checkout(repo_root, "HEAD") as base_root:
        assert repo_root not in base_root.parents
        assert base_root.resolve() != repo_root.resolve()


def test_pristine_checkout_removes_scratch_worktree(tmp_path: Path) -> None:
    repo = _init_repo(tmp_path)

    with pristine_checkout(tmp_path, "HEAD") as base_root:
        scratch_parent = base_root.parent
        assert base_root.is_dir()

    assert not base_root.exists()
    assert not scratch_parent.exists()

    porcelain = repo.git.worktree("list", "--porcelain")
    assert porcelain.count("worktree ") == 1


def test_pristine_checkout_unresolvable_rev_raises_and_leaves_no_worktree(
    tmp_path: Path,
) -> None:
    repo = _init_repo(tmp_path)

    with pytest.raises(DeltaError):
        with pristine_checkout(tmp_path, "no-such-rev"):
            pass

    porcelain = repo.git.worktree("list", "--porcelain")
    assert porcelain.count("worktree ") == 1


def test_pristine_checkout_no_git_repo_raises(tmp_path: Path) -> None:
    with pytest.raises(DeltaError):
        with pristine_checkout(tmp_path, "HEAD"):
            pass


def _config(*, source_roots: list[str] | None = None) -> IrminsulConfig:
    return IrminsulConfig(paths=Paths(docs_root="docs", source_roots=source_roots or ["src"]))


def _seed_repo(root: Path) -> None:
    """Init a repo and release its handles. The layout tests only need the
    `.git` entry to exist; holding the `Repo` open leaks a git subprocess whose
    later collection raises ResourceWarning, which `filterwarnings = ["error"]`
    turns into a failure in an unrelated test."""
    _init_repo(root).close()


def _tree(root: Path, rel: str) -> Path:
    path = root / rel
    path.mkdir(parents=True, exist_ok=True)
    return path


def test_cross_repo_trees_empty_when_everything_is_one_repo(tmp_path: Path) -> None:
    _seed_repo(tmp_path)
    _tree(tmp_path, "docs")
    _tree(tmp_path, "src")

    assert cross_repo_trees(tmp_path, _config()) == []


def test_cross_repo_trees_flags_the_siblings_layout(tmp_path: Path) -> None:
    """The docs repo and the code repo are separate repositories under one
    parent, so `git worktree add` on the docs repo cannot produce the code
    tree that `source_roots` reach through `../`."""
    docs_root = _tree(tmp_path, "workspace/docs")
    _seed_repo(docs_root)
    _tree(docs_root, "docs")
    _seed_repo(_tree(tmp_path, "workspace/code"))
    _tree(tmp_path, "workspace/code/src")

    assert cross_repo_trees(docs_root, _config(source_roots=["../code/src"])) == ["../code/src"]


def test_cross_repo_trees_flags_every_offending_root(tmp_path: Path) -> None:
    """Ownership is decided per configured root, so a layout with more than one
    sibling source root names them all rather than stopping at the first."""
    docs_root = _tree(tmp_path, "workspace/docs")
    _seed_repo(docs_root)
    _tree(docs_root, "docs")
    _seed_repo(_tree(tmp_path, "workspace/code"))
    _tree(tmp_path, "workspace/code/src")
    _tree(tmp_path, "workspace/code/lib")

    assert cross_repo_trees(docs_root, _config(source_roots=["../code/src", "../code/lib"])) == [
        "../code/src",
        "../code/lib",
    ]


def test_cross_repo_trees_skips_a_root_missing_on_disk(tmp_path: Path) -> None:
    """A configured root that does not exist says nothing about topology; the
    source walk already reports it as a missing root."""
    _seed_repo(tmp_path)
    _tree(tmp_path, "docs")

    assert cross_repo_trees(tmp_path, _config(source_roots=["nope"])) == []


def test_cross_repo_trees_ignores_an_unconfigured_nested_repo(tmp_path: Path) -> None:
    """Only configured roots are inspected, so a vendored checkout that happens
    to carry its own .git never trips the guard."""
    _seed_repo(tmp_path)
    _tree(tmp_path, "docs")
    _tree(tmp_path, "src")
    _seed_repo(_tree(tmp_path, "vendor/third-party"))

    assert cross_repo_trees(tmp_path, _config()) == []


def test_cross_repo_trees_flags_a_docs_tree_owned_by_another_repository(tmp_path: Path) -> None:
    """`docs_root` is enumerated too. No supported layout puts it in its own
    repository, but an ordinary git submodule does, and `git worktree add`
    omits it from the base checkout exactly the way it omits a sibling code
    repo — so every pre-existing finding in the docs tree would come back as
    new. Refusing is recoverable; a confidently inverted answer is not."""
    _seed_repo(tmp_path)
    docs = _tree(tmp_path, "docs")
    _seed_repo(docs)
    _tree(tmp_path, "src")

    assert cross_repo_trees(tmp_path, _config()) == ["docs"]
    with pytest.raises(DeltaError, match="cannot compare across a repository boundary"):
        verify_single_repo_topology(tmp_path, _config())


def test_verify_single_repo_topology_passes_for_one_repo(tmp_path: Path) -> None:
    _seed_repo(tmp_path)
    _tree(tmp_path, "docs")
    _tree(tmp_path, "src")

    verify_single_repo_topology(tmp_path, _config())


def test_verify_single_repo_topology_raises_naming_the_offending_root(tmp_path: Path) -> None:
    docs_root = _tree(tmp_path, "workspace/docs")
    _seed_repo(docs_root)
    _tree(docs_root, "docs")
    _seed_repo(_tree(tmp_path, "workspace/code"))
    _tree(tmp_path, "workspace/code/src")

    with pytest.raises(DeltaError) as excinfo:
        verify_single_repo_topology(docs_root, _config(source_roots=["../code/src"]))

    message = str(excinfo.value)
    assert "cannot compare across a repository boundary" in message
    assert "'../code/src'" in message
    assert "without --delta" in message


def test_pristine_checkout_yields_a_fully_resolved_root(tmp_path: Path) -> None:
    """The yielded root becomes `build_graph`'s `repo_root`, and the doc walk
    produces resolved paths. If the system temp dir is a symlink (macOS) or an
    8.3 short name (Windows), an unresolved root makes `relative_to` raise for
    every doc found — a failure invisible on Linux, where /tmp is a real dir."""
    _seed_repo(tmp_path)

    with pristine_checkout(tmp_path, "HEAD") as base_root:
        assert base_root == base_root.resolve()
