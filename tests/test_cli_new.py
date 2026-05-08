"""Tests for `irminsul new adr/component/rfc`."""

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
        'project_name = "r"\n[paths]\ndocs_root = "docs"\nsource_roots = []\n',
        encoding="utf-8",
    )
    (repo / "docs").mkdir()
    return repo


def test_new_adr_creates_file(tmp_path: Path) -> None:
    repo = _make_repo(tmp_path)
    result = runner.invoke(app, ["new", "adr", "Adopt LiteLLM", "--path", str(repo)])
    assert result.exit_code == 0, result.output
    adr_dir = repo / "docs" / "50-decisions"
    adrs = list(adr_dir.glob("*.md"))
    assert len(adrs) == 1
    assert "adopt-litellm" in adrs[0].name


def test_new_adr_passes_frontmatter_check(tmp_path: Path) -> None:
    repo = _make_repo(tmp_path)
    runner.invoke(app, ["new", "adr", "Test Decision", "--path", str(repo)])
    config = load(find_config(repo))
    graph = build_graph(repo, config)
    findings = FrontmatterCheck().run(graph)
    errors = [f for f in findings if f.severity.value == "error"]
    assert errors == [], errors


def test_new_adr_sequential_numbering(tmp_path: Path) -> None:
    repo = _make_repo(tmp_path)
    runner.invoke(app, ["new", "adr", "First", "--path", str(repo)])
    runner.invoke(app, ["new", "adr", "Second", "--path", str(repo)])
    adrs = sorted((repo / "docs" / "50-decisions").glob("*.md"))
    assert adrs[0].name.startswith("0001-")
    assert adrs[1].name.startswith("0002-")


def test_new_component_creates_file(tmp_path: Path) -> None:
    repo = _make_repo(tmp_path)
    result = runner.invoke(app, ["new", "component", "Composer", "--path", str(repo)])
    assert result.exit_code == 0, result.output
    dest = repo / "docs" / "20-components" / "composer.md"
    assert dest.exists()


def test_new_component_passes_frontmatter_check(tmp_path: Path) -> None:
    repo = _make_repo(tmp_path)
    runner.invoke(app, ["new", "component", "Foo Bar", "--path", str(repo)])
    config = load(find_config(repo))
    graph = build_graph(repo, config)
    findings = FrontmatterCheck().run(graph)
    errors = [f for f in findings if f.severity.value == "error"]
    assert errors == [], errors


def test_new_rfc_creates_file(tmp_path: Path) -> None:
    repo = _make_repo(tmp_path)
    result = runner.invoke(app, ["new", "rfc", "Switch to event sourcing", "--path", str(repo)])
    assert result.exit_code == 0, result.output
    rfcs = list((repo / "docs" / "80-evolution" / "rfcs").glob("*.md"))
    assert len(rfcs) == 1
    assert "switch-to-event-sourcing" in rfcs[0].name


def test_new_existing_file_exits_nonzero(tmp_path: Path) -> None:
    repo = _make_repo(tmp_path)
    runner.invoke(app, ["new", "component", "Foo", "--path", str(repo)])
    result = runner.invoke(app, ["new", "component", "Foo", "--path", str(repo)])
    assert result.exit_code != 0


def test_new_force_overwrites(tmp_path: Path) -> None:
    repo = _make_repo(tmp_path)
    runner.invoke(app, ["new", "component", "Foo", "--path", str(repo)])
    result = runner.invoke(app, ["new", "component", "Foo", "--force", "--path", str(repo)])
    assert result.exit_code == 0
