"""Tests for `irminsul new adr/component/rfc`."""

from __future__ import annotations

from pathlib import Path

from typer.testing import CliRunner

from irminsul.checks.frontmatter import FrontmatterCheck
from irminsul.checks.globs import GlobsCheck
from irminsul.checks.uniqueness import UniquenessCheck
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
    result = runner.invoke(app, ["new", "adr", "Adopt Hatchling", "--path", str(repo)])
    assert result.exit_code == 0, result.output
    adr_dir = repo / "docs" / "50-decisions"
    adrs = list(adr_dir.glob("*.md"))
    assert len(adrs) == 1
    assert "adopt-hatchling" in adrs[0].name


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


def _make_repo_with_sources(tmp_path: Path) -> Path:
    repo = tmp_path / "r"
    repo.mkdir()
    (repo / "irminsul.toml").write_text(
        'project_name = "r"\n[paths]\ndocs_root = "docs"\nsource_roots = ["app"]\n',
        encoding="utf-8",
    )
    (repo / "docs").mkdir()
    (repo / "app").mkdir()
    (repo / "app" / "composer.py").write_text("def compose():\n    pass\n", encoding="utf-8")
    (repo / "tests").mkdir()
    (repo / "tests" / "test_composer.py").write_text(
        "def test_compose():\n    pass\n", encoding="utf-8"
    )
    return repo


def test_new_component_describes_and_tests_populate_frontmatter(tmp_path: Path) -> None:
    repo = _make_repo_with_sources(tmp_path)
    result = runner.invoke(
        app,
        [
            "new",
            "component",
            "Composer",
            "--describes",
            "app/composer.py",
            "--tests",
            "tests/test_composer.py",
            "--path",
            str(repo),
        ],
    )
    assert result.exit_code == 0, result.output

    config = load(find_config(repo))
    graph = build_graph(repo, config)
    node = graph.nodes["composer"]
    assert node.frontmatter.describes == ["app/composer.py"]
    assert node.frontmatter.tests == ["tests/test_composer.py"]

    errors = [f for f in FrontmatterCheck().run(graph) if f.severity.value == "error"]
    assert errors == [], errors


def test_new_component_describes_actually_claims_the_file(tmp_path: Path) -> None:
    repo = _make_repo_with_sources(tmp_path)
    runner.invoke(
        app,
        ["new", "component", "Composer", "--describes", "app/composer.py", "--path", str(repo)],
    )
    config = load(find_config(repo))
    graph = build_graph(repo, config)
    assert GlobsCheck().run(graph) == []
    # No duplication error and no omission warning: the file is claimed.
    assert UniquenessCheck().run(graph) == []


def test_new_component_repeatable_options(tmp_path: Path) -> None:
    repo = _make_repo_with_sources(tmp_path)
    (repo / "app" / "mixer.py").write_text("def mix():\n    pass\n", encoding="utf-8")
    result = runner.invoke(
        app,
        [
            "new",
            "component",
            "Audio",
            "--describes",
            "app/composer.py",
            "--describes",
            "app/mixer.py",
            "--path",
            str(repo),
        ],
    )
    assert result.exit_code == 0, result.output
    config = load(find_config(repo))
    graph = build_graph(repo, config)
    assert graph.nodes["audio"].frontmatter.describes == ["app/composer.py", "app/mixer.py"]


def test_new_component_nonexistent_path_warns_but_writes(tmp_path: Path) -> None:
    repo = _make_repo_with_sources(tmp_path)
    result = runner.invoke(
        app,
        ["new", "component", "Ghost", "--describes", "app/ghost.py", "--path", str(repo)],
    )
    assert result.exit_code == 0, result.output
    assert "path does not exist: app/ghost.py" in result.output
    content = (repo / "docs" / "20-components" / "ghost.md").read_text(encoding="utf-8")
    assert "app/ghost.py" in content


def test_new_component_normalizes_backslash_paths(tmp_path: Path) -> None:
    repo = _make_repo_with_sources(tmp_path)
    result = runner.invoke(
        app,
        ["new", "component", "Composer", "--describes", "app\\composer.py", "--path", str(repo)],
    )
    assert result.exit_code == 0, result.output
    config = load(find_config(repo))
    graph = build_graph(repo, config)
    assert graph.nodes["composer"].frontmatter.describes == ["app/composer.py"]


def test_new_component_without_flags_keeps_empty_lists(tmp_path: Path) -> None:
    repo = _make_repo(tmp_path)
    runner.invoke(app, ["new", "component", "Bare", "--path", str(repo)])
    content = (repo / "docs" / "20-components" / "bare.md").read_text(encoding="utf-8")
    assert "describes: []" in content
    assert "tests: []" in content


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


def test_new_component_glob_describes_does_not_false_warn(tmp_path: Path) -> None:
    repo = _make_repo(tmp_path)
    (repo / "src" / "pkg").mkdir(parents=True)
    (repo / "src" / "pkg" / "a.py").write_text("x = 1\n", encoding="utf-8")
    result = runner.invoke(
        app,
        [
            "new",
            "component",
            "Pkg",
            "--describes",
            "src/pkg/**/*.py",
            "--path",
            str(repo),
        ],
    )
    assert result.exit_code == 0, result.output
    assert "does not exist" not in result.output


def test_new_component_glob_matching_nothing_still_warns(tmp_path: Path) -> None:
    repo = _make_repo(tmp_path)
    result = runner.invoke(
        app,
        ["new", "component", "Ghost", "--describes", "src/ghost/**/*.py", "--path", str(repo)],
    )
    assert result.exit_code == 0, result.output
    assert "does not exist" in result.output


_TYPER_TOOL = (
    "import typer\n"
    "app = typer.Typer()\n"
    "\n"
    '@app.command("ingest")\n'
    "def ingest() -> None:\n"
    "    pass\n"
    "\n"
    "@app.command()\n"
    "def export_all() -> None:\n"
    "    pass\n"
)


def _make_repo_with_cli_tool(tmp_path: Path) -> Path:
    repo = tmp_path / "r"
    repo.mkdir()
    (repo / "irminsul.toml").write_text(
        'project_name = "r"\n[paths]\ndocs_root = "docs"\nsource_roots = ["src"]\n',
        encoding="utf-8",
    )
    (repo / "docs").mkdir()
    (repo / "src").mkdir()
    (repo / "src" / "tool.py").write_text(_TYPER_TOOL, encoding="utf-8")
    return repo


def test_new_component_from_surface_prefills_surface_section(tmp_path: Path) -> None:
    repo = _make_repo_with_cli_tool(tmp_path)
    result = runner.invoke(
        app,
        [
            "new",
            "component",
            "Tool",
            "--describes",
            "src/tool.py",
            "--from-surface",
            "--path",
            str(repo),
        ],
    )
    assert result.exit_code == 0, result.output
    body = (repo / "docs" / "20-components" / "tool.md").read_text(encoding="utf-8")
    assert "## Surface" in body
    assert "### cli" in body
    assert "`ingest`" in body
    assert "`export-all`" in body  # implicit typer naming, underscores to dashes
    assert "[`src/tool.py`](../../src/tool.py)" in body
    # the Surface section sits above Scope & Limitations
    assert body.index("## Surface") < body.index("## Scope & Limitations")


def test_new_component_without_from_surface_has_no_surface_section(tmp_path: Path) -> None:
    repo = _make_repo_with_cli_tool(tmp_path)
    result = runner.invoke(
        app,
        ["new", "component", "Tool", "--describes", "src/tool.py", "--path", str(repo)],
    )
    assert result.exit_code == 0, result.output
    body = (repo / "docs" / "20-components" / "tool.md").read_text(encoding="utf-8")
    assert "## Surface" not in body


def test_new_component_from_surface_requires_describes(tmp_path: Path) -> None:
    repo = _make_repo_with_cli_tool(tmp_path)
    result = runner.invoke(app, ["new", "component", "Tool", "--from-surface", "--path", str(repo)])
    assert result.exit_code == 2
    assert "--describes" in result.output


def test_new_component_from_surface_degrades_for_plain_modules(tmp_path: Path) -> None:
    repo = _make_repo_with_cli_tool(tmp_path)
    (repo / "src" / "plain.py").write_text("def helper() -> int:\n    return 1\n", encoding="utf-8")
    result = runner.invoke(
        app,
        [
            "new",
            "component",
            "Plain",
            "--describes",
            "src/plain.py",
            "--from-surface",
            "--path",
            str(repo),
        ],
    )
    assert result.exit_code == 0, result.output
    assert "no derivable surface" in result.output
    body = (repo / "docs" / "20-components" / "plain.md").read_text(encoding="utf-8")
    assert "## Surface" not in body


def test_new_component_from_surface_doc_passes_checks(tmp_path: Path) -> None:
    repo = _make_repo_with_cli_tool(tmp_path)
    runner.invoke(
        app,
        [
            "new",
            "component",
            "Tool",
            "--describes",
            "src/tool.py",
            "--from-surface",
            "--path",
            str(repo),
        ],
    )
    config = load(find_config(repo))
    graph = build_graph(repo, config)
    for check in (FrontmatterCheck(), GlobsCheck(), UniquenessCheck()):
        errors = [f for f in check.run(graph) if f.severity.value == "error"]
        assert errors == [], (check, errors)
