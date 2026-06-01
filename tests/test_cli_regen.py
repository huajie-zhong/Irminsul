"""Tests for `irminsul regen`.

Only `regen agents-md` survives. The Python/TypeScript reference stubs and the
`regen all`/`docs-surfaces` aggregators were retired with the render subsystem
(RFC-0025) and under "derive, don't materialize" (RFC-0020); code-derivable
surfaces are now produced on demand via `irminsul surface <kind>`.
"""

from __future__ import annotations

from pathlib import Path

from typer.testing import CliRunner

from irminsul.cli import app

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


def test_regen_agents_md_creates_manifest(tmp_path: Path) -> None:
    repo = _make_repo(tmp_path)
    result = runner.invoke(app, ["regen", "agents-md", "--path", str(repo)])
    assert result.exit_code == 0, result.output
    manifest = repo / "docs" / "AGENTS.md"
    assert manifest.is_file()
    text = manifest.read_text(encoding="utf-8")
    assert "<!-- agents-manifest:generated-start -->" in text
    assert "<!-- agents-manifest:generated-end -->" in text
    assert "## Foundations" in text
    assert "## Protocol" in text


def test_regen_agents_md_preserves_curated_sections(tmp_path: Path) -> None:
    repo = _make_repo(tmp_path)
    runner.invoke(app, ["regen", "agents-md", "--path", str(repo)])
    manifest = repo / "docs" / "AGENTS.md"
    manifest.write_text(
        manifest.read_text(encoding="utf-8").replace(
            "## Foundations", "## Foundations\n\nCURATED EDIT SURVIVES"
        ),
        encoding="utf-8",
    )
    result = runner.invoke(app, ["regen", "agents-md", "--path", str(repo)])
    assert result.exit_code == 0, result.output
    assert "CURATED EDIT SURVIVES" in manifest.read_text(encoding="utf-8")


def test_regen_without_target_shows_help() -> None:
    result = runner.invoke(app, ["regen"])
    # `no_args_is_help` prints help; the exit code is 0 on older Click and 2 on
    # newer Click (which treats a missing subcommand as a usage error).
    assert result.exit_code in (0, 2)
    assert "agents-md" in result.output
    assert "agent-index" not in result.output


def test_regen_rejects_removed_language_flag(tmp_path: Path) -> None:
    repo = _make_repo(tmp_path)
    result = runner.invoke(app, ["regen", "--language", "python", "--path", str(repo)])
    assert result.exit_code != 0


def test_regen_agent_index_is_rejected(tmp_path: Path) -> None:
    repo = _make_repo(tmp_path)
    result = runner.invoke(app, ["regen", "agent-index", "--path", str(repo)])
    assert result.exit_code != 0


def test_regen_docs_surfaces_command_removed(tmp_path: Path) -> None:
    # Generated reference surfaces were retired under "derive, don't materialize";
    # the surface is now derived on demand via `irminsul surface <kind>`.
    repo = _make_repo(tmp_path)
    result = runner.invoke(app, ["regen", "docs-surfaces", "--path", str(repo)])
    assert result.exit_code != 0


def test_regen_python_command_removed(tmp_path: Path) -> None:
    # Retired with the render subsystem (RFC-0025): the mkdocstrings stubs had no
    # consumer once the renderer was gone.
    repo = _make_repo(tmp_path)
    result = runner.invoke(app, ["regen", "python", "--path", str(repo)])
    assert result.exit_code != 0


def test_regen_typescript_command_removed(tmp_path: Path) -> None:
    repo = _make_repo(tmp_path)
    result = runner.invoke(app, ["regen", "typescript", "--path", str(repo)])
    assert result.exit_code != 0


def test_regen_all_command_removed(tmp_path: Path) -> None:
    repo = _make_repo(tmp_path)
    result = runner.invoke(app, ["regen", "all", "--path", str(repo)])
    assert result.exit_code != 0
