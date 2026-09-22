"""Tests for the init/detector heuristics."""

from __future__ import annotations

from pathlib import Path

from irminsul.init.detector import detect_languages, detect_source_roots


def test_detects_python_from_pyproject(tmp_path: Path) -> None:
    (tmp_path / "pyproject.toml").write_text("[project]\nname = 'demo'\n")
    assert detect_languages(tmp_path) == ["python"]


def test_detects_python_from_requirements(tmp_path: Path) -> None:
    (tmp_path / "requirements.txt").write_text("requests==2.32.0\n")
    assert detect_languages(tmp_path) == ["python"]


def test_detects_typescript_from_package_and_tsconfig(tmp_path: Path) -> None:
    (tmp_path / "package.json").write_text("{}")
    (tmp_path / "tsconfig.json").write_text("{}")
    assert detect_languages(tmp_path) == ["typescript"]


def test_polyglot_detects_both(tmp_path: Path) -> None:
    (tmp_path / "pyproject.toml").write_text("[project]\nname = 'demo'\n")
    (tmp_path / "package.json").write_text("{}")
    (tmp_path / "tsconfig.json").write_text("{}")
    assert set(detect_languages(tmp_path)) == {"python", "typescript"}


def test_empty_repo_detects_nothing(tmp_path: Path) -> None:
    assert detect_languages(tmp_path) == []


def test_source_roots_picks_existing_dirs(tmp_path: Path) -> None:
    (tmp_path / "src").mkdir()
    (tmp_path / "lib").mkdir()
    roots = detect_source_roots(tmp_path, ["python"])
    assert "src" in roots
    assert "lib" in roots


def test_source_roots_falls_back_to_src(tmp_path: Path) -> None:
    roots = detect_source_roots(tmp_path, ["python"])
    assert roots == ["src"]
