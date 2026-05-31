"""Tests for `irminsul surface` and static-vs-live CLI extraction agreement."""

from __future__ import annotations

import json
from pathlib import Path

from pathspec import GitIgnoreSpec
from typer.testing import CliRunner

from irminsul.checks.globs import walk_source_files
from irminsul.cli import app
from irminsul.config import IrminsulConfig
from irminsul.inventory import get_extractor

runner = CliRunner()

CLI_SRC = """\
import typer

app = typer.Typer()


@app.command()
def alpha():
    pass


@app.command()
def beta():
    pass
"""


def _repo(tmp_path: Path) -> Path:
    repo = tmp_path / "r"
    (repo / "src").mkdir(parents=True)
    (repo / "irminsul.toml").write_text(
        'project_name = "r"\n[paths]\ndocs_root = "docs"\nsource_roots = ["src"]\n',
        encoding="utf-8",
    )
    (repo / "src" / "cli.py").write_text(CLI_SRC, encoding="utf-8")
    return repo


def test_surface_plain_lists_identities(tmp_path: Path) -> None:
    repo = _repo(tmp_path)
    result = runner.invoke(app, ["surface", "cli", "--path", str(repo)])
    assert result.exit_code == 0, result.output
    assert "alpha" in result.output
    assert "beta" in result.output


def test_surface_json_format(tmp_path: Path) -> None:
    repo = _repo(tmp_path)
    result = runner.invoke(app, ["surface", "cli", "--format", "json", "--path", str(repo)])
    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert {row["identity"] for row in payload} == {"alpha", "beta"}


def test_surface_unknown_kind_errors(tmp_path: Path) -> None:
    repo = _repo(tmp_path)
    result = runner.invoke(app, ["surface", "bogus", "--path", str(repo)])
    assert result.exit_code == 2


def _live_leaf_commands(command, prefix: str = "") -> set[str]:
    from typer.main import get_command

    root = get_command(command) if prefix == "" else command
    out: set[str] = set()
    children = getattr(root, "commands", None)
    if isinstance(children, dict):
        for name, child in children.items():
            full = f"{prefix} {name}".strip()
            if isinstance(getattr(child, "commands", None), dict):
                out |= _live_leaf_commands(child, full)
            else:
                out.add(full)
    return out


def test_static_extractor_agrees_with_live_typer() -> None:
    """The static CLI extractor must match Typer's real command resolution for irminsul."""
    repo = Path(__file__).resolve().parents[1]
    cfg = IrminsulConfig()
    files, _ = walk_source_files(repo, ["src/irminsul"])
    spec = GitIgnoreSpec.from_lines(["src/irminsul/cli.py"])
    files = [(p, d) for p, d in files if spec.match_file(d)]
    static = {item.identity for item in get_extractor("cli", cfg).extract(files, cfg)}
    live = _live_leaf_commands(app)
    assert static == live
