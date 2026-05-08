"""Tests for `irminsul regen reference`."""

from __future__ import annotations

from pathlib import Path

from typer.testing import CliRunner

from irminsul.checks.frontmatter import FrontmatterCheck
from irminsul.cli import app
from irminsul.config import find_config, load
from irminsul.docgraph import build_graph

runner = CliRunner()


def _make_repo(tmp_path: Path) -> Path:
    repo = tmp_path / "r"
    repo.mkdir()
    (repo / "irminsul.toml").write_text(
        'project_name = "r"\n[paths]\ndocs_root = "docs"\nsource_roots = ["src"]\n',
        encoding="utf-8",
    )
    src = repo / "src" / "mylib"
    src.mkdir(parents=True)
    (src / "__init__.py").write_text("", encoding="utf-8")
    (src / "core.py").write_text("def run(): pass\n", encoding="utf-8")
    (repo / "docs").mkdir()
    return repo


def test_regen_python_creates_stubs(tmp_path: Path) -> None:
    repo = _make_repo(tmp_path)
    result = runner.invoke(app, ["regen", "--language", "python", "--path", str(repo)])
    assert result.exit_code == 0, result.output
    stubs = list((repo / "docs" / "40-reference" / "python").rglob("*.md"))
    names = [s.stem for s in stubs]
    # core.py → stub; __init__.py → skipped (underscore prefix)
    assert "core" in names
    assert "__init__" not in names


def test_regen_python_stub_has_valid_frontmatter(tmp_path: Path) -> None:
    repo = _make_repo(tmp_path)
    runner.invoke(app, ["regen", "--language", "python", "--path", str(repo)])
    config = load(find_config(repo))
    graph = build_graph(repo, config)
    findings = FrontmatterCheck().run(graph)
    errors = [f for f in findings if f.severity.value == "error"]
    assert errors == [], errors


def test_regen_typescript_deferred(tmp_path: Path) -> None:
    repo = _make_repo(tmp_path)
    result = runner.invoke(app, ["regen", "--language", "typescript", "--path", str(repo)])
    assert result.exit_code == 0
    assert "deferred" in result.output.lower() or "Sprint 3" in result.output


def test_regen_idempotent(tmp_path: Path) -> None:
    repo = _make_repo(tmp_path)
    runner.invoke(app, ["regen", "--language", "python", "--path", str(repo)])
    stubs_before = sorted(p.name for p in (repo / "docs" / "40-reference" / "python").rglob("*.md"))
    runner.invoke(app, ["regen", "--language", "python", "--path", str(repo)])
    stubs_after = sorted(p.name for p in (repo / "docs" / "40-reference" / "python").rglob("*.md"))
    assert stubs_before == stubs_after
