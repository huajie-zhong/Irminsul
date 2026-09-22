"""Tests for `irminsul new adr/component/rfc`."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest
from typer.testing import CliRunner

from irminsul.checks.frontmatter import FrontmatterCheck
from irminsul.checks.globs import GlobsCheck
from irminsul.checks.uniqueness import UniquenessCheck
from irminsul.cli import app
from irminsul.config import find_config, load
from irminsul.docgraph import build_graph

from .conftest import cli_output

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
    adr_dir = repo / "docs" / "decisions"
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


def test_new_adr_has_canonical_sections(tmp_path: Path) -> None:
    repo = _make_repo(tmp_path)
    runner.invoke(app, ["new", "adr", "Test Decision", "--path", str(repo)])
    [adr] = (repo / "docs" / "decisions").glob("*.md")
    text = adr.read_text(encoding="utf-8")
    for heading in (
        "## Status",
        "## Context",
        "## Decision",
        "## Alternatives Considered",
        "## Consequences",
    ):
        assert text.count(heading) == 1


def test_new_adr_is_named_by_slug_and_refuses_a_taken_name(tmp_path: Path) -> None:
    repo = _make_repo(tmp_path)
    first = runner.invoke(app, ["new", "adr", "Cache Sharding", "--path", str(repo)])
    assert first.exit_code == 0, first.output
    assert (repo / "docs" / "decisions" / "cache-sharding.md").is_file()

    again = runner.invoke(app, ["new", "adr", "Cache sharding", "--path", str(repo)])
    assert again.exit_code != 0


def test_new_component_creates_file(tmp_path: Path) -> None:
    repo = _make_repo(tmp_path)
    result = runner.invoke(app, ["new", "component", "Composer", "--path", str(repo)])
    assert result.exit_code == 0, result.output
    dest = repo / "docs" / "components" / "composer.md"
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
    rfcs = list((repo / "docs" / "rfcs").glob("*.md"))
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
    assert node.frontmatter.recommended_tests == ["tests/test_composer.py"]
    assert node.frontmatter.tests == []  # the legacy spelling is not written any more

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
    content = (repo / "docs" / "components" / "ghost.md").read_text(encoding="utf-8")
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
    content = (repo / "docs" / "components" / "bare.md").read_text(encoding="utf-8")
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
    body = (repo / "docs" / "components" / "tool.md").read_text(encoding="utf-8")
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
    body = (repo / "docs" / "components" / "tool.md").read_text(encoding="utf-8")
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
    body = (repo / "docs" / "components" / "plain.md").read_text(encoding="utf-8")
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


def test_console_entry_point_passes_glob_arguments_through(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from irminsul.cli import main

    (tmp_path / "src" / "pkg").mkdir(parents=True)
    (tmp_path / "src" / "pkg" / "a.py").write_text("x = 1\n", encoding="utf-8")
    (tmp_path / "irminsul.toml").write_text(
        '[paths]\ndocs_root = "docs"\nsource_roots = ["src"]\n', encoding="utf-8"
    )
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "irminsul",
            "new",
            "component",
            "widget",
            "--describes",
            "src/**",
            "--path",
            str(tmp_path),
        ],
    )
    with pytest.raises(SystemExit) as exc:
        main()
    assert exc.value.code in (0, None)
    doc = (tmp_path / "docs" / "components" / "widget.md").read_text(encoding="utf-8")
    assert "src/**" in doc


def _owned(tmp_path: Path) -> Path:
    repo = _make_repo(tmp_path)
    (repo / "irminsul.toml").write_text(
        'project_name = "r"\n[paths]\ndocs_root = "docs"\nsource_roots = ["src"]\n',
        encoding="utf-8",
    )
    (repo / "src").mkdir()
    (repo / "src" / "a.py").write_text("A = 1\n", encoding="utf-8")
    (repo / "docs" / "components").mkdir()
    (repo / "docs" / "components" / "big.md").write_text(
        "---\nid: big\ntitle: Big\nstatus: stable\ndescribes:\n  - src/*.py\n---\n\n# Big\n",
        encoding="utf-8",
    )
    return repo


def test_new_component_refuses_files_another_doc_owns(tmp_path: Path) -> None:
    repo = _owned(tmp_path)
    args = ["new", "component", "Small", "--describes", "src/a.py", "--path", str(repo)]
    result = runner.invoke(app, args)
    assert result.exit_code == 1
    assert "big: src/a.py" in result.output
    assert not (repo / "docs" / "components" / "small.md").exists()


def test_new_component_split_from_links_the_owner(tmp_path: Path) -> None:
    repo = _owned(tmp_path)
    args = ["new", "component", "Small", "--describes", "src/a.py", "--split-from", "big"]
    result = runner.invoke(app, [*args, "--path", str(repo)])
    assert result.exit_code == 0, result.output
    text = (repo / "docs" / "components" / "small.md").read_text(encoding="utf-8")
    assert "Split from [Big](big.md)." in text
    assert "remove src/a.py from big's describes" in result.output


def test_new_component_split_from_an_unknown_doc_is_a_usage_error(tmp_path: Path) -> None:
    repo = _owned(tmp_path)
    args = ["new", "component", "Other", "--split-from", "nope", "--path", str(repo)]
    assert runner.invoke(app, args).exit_code == 2


def test_new_refuses_an_id_another_doc_uses(tmp_path: Path) -> None:
    repo = _owned(tmp_path)
    result = runner.invoke(app, ["new", "adr", "Big", "--path", str(repo)])
    assert result.exit_code == 1
    assert "already used by docs/components/big.md" in result.output


def test_new_writes_quoted_and_non_ascii_titles_that_parse(tmp_path: Path) -> None:
    repo = _make_repo(tmp_path)
    for title in ['Say "hi" there', "使用 Python"]:
        assert runner.invoke(app, ["new", "adr", title, "--path", str(repo)]).exit_code == 0
    graph = build_graph(repo, load(find_config(repo)))
    assert {node.frontmatter.title for node in graph.nodes.values()} >= {
        'Say "hi" there',
        "使用 Python",
    }
    assert "python" in graph.nodes


def test_new_from_a_subdirectory_is_a_usage_error(tmp_path: Path) -> None:
    repo = _make_repo(tmp_path)
    result = runner.invoke(app, ["new", "adr", "X", "--path", str(repo / "docs")])
    assert result.exit_code == 2
    assert not (repo / "docs" / "docs").exists()


def test_from_surface_links_resolve_under_a_nested_layer(tmp_path: Path) -> None:
    repo = _make_repo(tmp_path)
    (repo / "irminsul.toml").write_text(
        'project_name = "r"\n[paths]\ndocs_root = "site/docs"\nsource_roots = ["src"]\n'
        '[layers.components]\npath = "sys/components"\n',
        encoding="utf-8",
    )
    (repo / "src").mkdir()
    (repo / "src" / "core.py").write_text("import os\nos.environ.get('CORE_HOME')\n", "utf-8")
    args = ["new", "component", "Core", "--describes", "src/core.py", "--from-surface"]
    assert runner.invoke(app, [*args, "--path", str(repo)]).exit_code == 0
    doc = repo / "site" / "docs" / "sys" / "components" / "core.md"
    assert "](../../../../src/core.py)" in doc.read_text(encoding="utf-8")


@pytest.mark.parametrize("title", ["文档模型", "...", "!!!"])
def test_a_title_that_slugifies_to_nothing_is_refused(tmp_path: Path, title: str) -> None:
    """It used to write `docs/decisions/.md`, a dot-file no listing shows."""
    repo = _make_repo(tmp_path)
    (repo / "docs" / "decisions").mkdir()

    result = runner.invoke(app, ["new", "adr", title, "--path", str(repo)])

    assert result.exit_code != 0
    assert not list((repo / "docs" / "decisions").glob("*.md"))
    assert not (repo / "docs" / "decisions" / ".md").exists()


def test_a_bracket_in_a_title_does_not_break_the_index_link(tmp_path: Path) -> None:
    """`- [Foo] bar](foo-bar.md)` was a broken link no run could repair."""
    repo = _make_repo(tmp_path)
    decisions = repo / "docs" / "decisions"
    decisions.mkdir()
    (decisions / "INDEX.md").write_text(
        "---\nid: decisions\ntitle: D\nstatus: stable\n---\n\n# D\n", encoding="utf-8"
    )

    result = runner.invoke(app, ["new", "adr", "Foo] bar", "--path", str(repo)])
    assert result.exit_code == 0, result.output

    index = (decisions / "INDEX.md").read_text(encoding="utf-8")
    assert r"- [Foo\] bar](foo-bar.md)" in index
    assert "[Foo] bar]" not in index


def test_frontmatter_values_are_yaml_escaped(tmp_path: Path) -> None:
    """The template quoted `describes` values by hand and passed the title through
    `tojson`, which is JSON's idea of a string, not YAML's.

    A quote in a path broke the block; a newline injected whatever keys followed it;
    and `json.dumps` escapes an emoji as a surrogate pair, which YAML cannot parse.
    """
    import frontmatter

    repo = _make_repo(tmp_path)
    emoji_title = "Payments " + chr(0x1F4B8) + " service"
    result = runner.invoke(app, ["new", "component", emoji_title, "--path", str(repo)])
    assert result.exit_code == 0, result.output
    doc = repo / "docs" / "components" / "payments-service.md"
    assert frontmatter.load(doc).metadata["title"] == emoji_title

    injected = 'app/thing.py"' + chr(10) + "status: stable"
    result = runner.invoke(
        app, ["new", "component", "Injector", "--describes", injected, "--path", str(repo)]
    )
    assert result.exit_code == 0, result.output
    meta = frontmatter.load(repo / "docs" / "components" / "injector.md").metadata
    assert meta["status"] == "draft", "a describes value set a frontmatter key"
    assert meta["describes"] == [injected]


def test_new_refuses_a_title_that_would_take_the_layer_index(tmp_path: Path) -> None:
    """On a case-insensitive filesystem `index.md` *is* `INDEX.md`, so the existence
    guard saw the layer index and `--force` overwrote it — taking its links with it and
    reporting a path that then did not exist."""
    repo = _make_repo(tmp_path)
    index = repo / "docs" / "components" / "INDEX.md"
    index.parent.mkdir(parents=True, exist_ok=True)
    index.write_text(
        "---\nid: components\ntitle: Components\nstatus: stable\n---\n\n"
        "# Components\n\n- [Composer](composer.md)\n",
        encoding="utf-8",
    )
    before = index.read_text(encoding="utf-8")

    for title in ("Index", "index", "INDEX"):
        result = runner.invoke(app, ["new", "component", title, "--force", "--path", str(repo)])
        assert result.exit_code == 2, f"{title!r} was not refused"
        assert "INDEX.md" in cli_output(result)

    assert index.read_text(encoding="utf-8") == before
