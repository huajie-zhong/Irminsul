"""Unit tests for walk_source_files — same-repo and cross-repo (Topology B)."""

from __future__ import annotations

from pathlib import Path

from irminsul.checks.globs import walk_source_files


def _make_tree(base: Path, files: list[str]) -> None:
    for rel in files:
        p = base / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text("# placeholder")


def test_same_repo_returns_repo_relative_display(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    _make_tree(repo, ["src/a.py", "src/sub/b.py"])

    entries, missing = walk_source_files(repo, ["src"])

    assert not missing
    displays = {display for _, display in entries}
    assert "src/a.py" in displays
    assert "src/sub/b.py" in displays


def test_same_repo_abs_paths_are_absolute(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    _make_tree(repo, ["src/a.py"])

    entries, _ = walk_source_files(repo, ["src"])

    for abs_path, _ in entries:
        assert abs_path.is_absolute()


def test_cross_repo_display_is_source_root_relative(tmp_path: Path) -> None:
    docs = tmp_path / "docs"
    docs.mkdir()
    code = tmp_path / "code" / "src"
    _make_tree(code.parent, ["src/app.py", "src/sub/util.py"])

    entries, missing = walk_source_files(docs, ["../code/src"])

    assert not missing
    displays = {display for _, display in entries}
    assert "app.py" in displays
    assert "sub/util.py" in displays


def test_cross_repo_abs_path_points_to_code_file(tmp_path: Path) -> None:
    docs = tmp_path / "docs"
    docs.mkdir()
    code_src = tmp_path / "code" / "src"
    _make_tree(code_src.parent, ["src/app.py"])

    entries, _ = walk_source_files(docs, ["../code/src"])

    abs_paths = {abs_path for abs_path, _ in entries}
    assert any(p.name == "app.py" for p in abs_paths)
    for p in abs_paths:
        assert p.is_absolute()


def test_dot_directories_skipped_same_repo(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    _make_tree(repo, ["src/a.py", "src/.venv/hidden.py", ".git/config"])

    entries, _ = walk_source_files(repo, ["src"])

    displays = {display for _, display in entries}
    assert "src/a.py" in displays
    assert not any(".venv" in d for d in displays)


def test_python_bytecode_cache_skipped_same_repo(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    _make_tree(repo, ["src/a.py", "src/__pycache__/a.cpython-312.pyc"])

    entries, _ = walk_source_files(repo, ["src"])

    displays = {display for _, display in entries}
    assert "src/a.py" in displays
    assert not any("__pycache__" in d for d in displays)
    assert not any(d.endswith(".pyc") for d in displays)


def test_dot_directories_skipped_cross_repo(tmp_path: Path) -> None:
    docs = tmp_path / "docs"
    docs.mkdir()
    code = tmp_path / "code" / "src"
    _make_tree(code.parent, ["src/app.py", "src/.cache/data.py"])

    entries, _ = walk_source_files(docs, ["../code/src"])

    displays = {display for _, display in entries}
    assert "app.py" in displays
    assert not any(".cache" in d for d in displays)


def test_missing_root_reported(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()

    entries, missing = walk_source_files(repo, ["nonexistent"])

    assert entries == []
    assert "nonexistent" in missing


def test_multiple_roots_combined(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    _make_tree(repo, ["src/a.py", "lib/b.py"])

    entries, missing = walk_source_files(repo, ["src", "lib"])

    assert not missing
    displays = {display for _, display in entries}
    assert "src/a.py" in displays
    assert "lib/b.py" in displays
