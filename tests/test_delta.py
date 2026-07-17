"""Unit tests for `irminsul.delta`: fingerprint reuse and the scratch worktree."""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path

import pytest
from git import Repo

from irminsul.checks.base import Finding, Severity
from irminsul.delta import DeltaError, compute_delta, pristine_checkout


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
