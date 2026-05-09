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


def _make_typescript_repo(tmp_path: Path) -> Path:
    repo = tmp_path / "ts"
    repo.mkdir()
    (repo / "irminsul.toml").write_text(
        "\n".join(
            [
                'project_name = "ts"',
                "[paths]",
                'docs_root = "docs"',
                'source_roots = ["src"]',
                "[languages]",
                'enabled = ["typescript"]',
                "",
            ]
        ),
        encoding="utf-8",
    )
    src = repo / "src" / "ui"
    src.mkdir(parents=True)
    (src / "button.ts").write_text("export function Button() {}\n", encoding="utf-8")
    (src / "button.test.ts").write_text("test('x', () => {})\n", encoding="utf-8")
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


def test_regen_typescript_requires_typedoc(tmp_path: Path) -> None:
    repo = _make_typescript_repo(tmp_path)
    result = runner.invoke(app, ["regen", "--language", "typescript", "--path", str(repo)])
    assert result.exit_code == 1
    assert "TypeDoc" in result.output


def test_regen_typescript_creates_stubs(tmp_path: Path, monkeypatch) -> None:
    repo = _make_typescript_repo(tmp_path)

    import irminsul.regen.typescript as regen_typescript

    monkeypatch.setattr(regen_typescript, "_ensure_typedoc", lambda repo_root: None)
    result = runner.invoke(app, ["regen", "--language", "typescript", "--path", str(repo)])

    assert result.exit_code == 0, result.output
    stub = repo / "docs" / "40-reference" / "typescript" / "ui" / "button.md"
    assert stub.is_file()
    assert "id: ui-button" in stub.read_text(encoding="utf-8")
    assert not (repo / "docs" / "40-reference" / "typescript" / "ui" / "button.test.md").exists()


def test_regen_typescript_rejects_stub_collisions(tmp_path: Path, monkeypatch) -> None:
    repo = _make_typescript_repo(tmp_path)
    (repo / "src" / "ui" / "button.tsx").write_text("export function ButtonView() {}\n")

    import irminsul.regen.typescript as regen_typescript

    monkeypatch.setattr(regen_typescript, "_ensure_typedoc", lambda repo_root: None)
    result = runner.invoke(app, ["regen", "--language", "typescript", "--path", str(repo)])

    assert result.exit_code == 1
    assert "collision" in result.output


def test_regen_idempotent(tmp_path: Path) -> None:
    repo = _make_repo(tmp_path)
    runner.invoke(app, ["regen", "--language", "python", "--path", str(repo)])
    stubs_before = sorted(p.name for p in (repo / "docs" / "40-reference" / "python").rglob("*.md"))
    runner.invoke(app, ["regen", "--language", "python", "--path", str(repo)])
    stubs_after = sorted(p.name for p in (repo / "docs" / "40-reference" / "python").rglob("*.md"))
    assert stubs_before == stubs_after
