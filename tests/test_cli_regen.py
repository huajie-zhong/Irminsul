"""Tests for `irminsul regen`.

Only `regen agents-md` survives. The Python/TypeScript reference stubs and the
`regen all`/`docs-surfaces` aggregators were retired with the render subsystem and under "derive, don't materialize"; code-derivable
surfaces are now produced on demand via `irminsul surface <kind>`.
"""

from __future__ import annotations

from pathlib import Path

from typer.testing import CliRunner

from irminsul.cli import app

from .conftest import cli_output

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
    # Retired with the render subsystem: the mkdocstrings stubs had no
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


def test_regen_refuses_a_manifest_whose_markers_do_not_parse(tmp_path: Path) -> None:
    """A broken marker pair used to mean "rebuild from the default template", which
    deleted every curated section — including the paragraph promising they survive a
    regen. The `missing-generated-markers` finding suggests running this command, so the
    tool talked the reader into destroying their own file.
    """
    repo = _make_repo(tmp_path)
    runner.invoke(app, ["regen", "agents-md", "--path", str(repo)])
    manifest = repo / "docs" / "AGENTS.md"
    manifest.write_text(
        manifest.read_text(encoding="utf-8").replace("<!-- agents-manifest:generated-end -->", "")
        + "\n## Curated\n\nAuthored guidance that must survive.\n",
        encoding="utf-8",
    )
    before = manifest.read_text(encoding="utf-8")

    result = runner.invoke(app, ["regen", "agents-md", "--path", str(repo)])

    assert result.exit_code == 2
    assert "do not parse" in cli_output(result)
    assert manifest.read_text(encoding="utf-8") == before, "the manifest was rewritten"


def test_regen_refuses_a_manifest_that_is_not_utf8(tmp_path: Path) -> None:
    """`check` reports a UTF-16 manifest and its suggestion is to run this command, so
    arriving here and getting a traceback is the tool punishing the reader for following
    its own advice. Refuse, and say which repair is available."""
    repo = _make_repo(tmp_path)
    manifest = repo / "docs" / "AGENTS.md"
    runner.invoke(app, ["regen", "agents-md", "--path", str(repo)])
    manifest.write_text(manifest.read_text(encoding="utf-8"), encoding="utf-16")
    as_written = manifest.read_bytes()

    result = runner.invoke(app, ["regen", "agents-md", "--path", str(repo)])

    assert result.exit_code == 2
    assert "UnicodeDecodeError" not in result.output
    assert "not valid UTF-8" in result.output and "UTF-16" in result.output
    # The file is left exactly as it was: refusing is recoverable, rewriting is not.
    assert manifest.read_bytes() == as_written
