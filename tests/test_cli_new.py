"""Tests for `irminsul new adr/component/rfc`."""

from __future__ import annotations

import re
import sys
from pathlib import Path

import pytest
from click import unstyle
from typer.testing import CliRunner

from irminsul.checks.frontmatter import FrontmatterCheck
from irminsul.checks.globs import GlobsCheck
from irminsul.checks.uniqueness import UniquenessCheck
from irminsul.cli import app
from irminsul.frontmatter import read_frontmatter

from .conftest import check_findings, cli_output, load_graph, run_check, write_config

runner = CliRunner()


def _make_repo(tmp_path: Path) -> Path:
    repo = tmp_path / "r"
    repo.mkdir()
    write_config(repo)
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
    findings = run_check(FrontmatterCheck, repo)
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
    findings = run_check(FrontmatterCheck, repo)
    errors = [f for f in findings if f.severity.value == "error"]
    assert errors == [], errors


def test_new_rfc_creates_file(tmp_path: Path) -> None:
    repo = _make_repo(tmp_path)
    result = runner.invoke(app, ["new", "rfc", "Switch to event sourcing", "--path", str(repo)])
    assert result.exit_code == 0, result.output
    rfcs = list((repo / "docs" / "rfcs").glob("*.md"))
    assert len(rfcs) == 1
    assert "switch-to-event-sourcing" in rfcs[0].name


def test_new_rfc_scaffolds_over_a_failing_tree_and_force_only_overwrites(
    tmp_path: Path,
) -> None:
    """An unrelated error used to block drafting unless `--force`, and `--force` also
    overwrote the file, so getting past the error could clobber a drafted RFC."""
    repo = _make_repo(tmp_path)
    (repo / "docs" / "broken.md").write_text("# no frontmatter\n", encoding="utf-8")
    args = ["new", "rfc", "Switch to event sourcing", "--path", str(repo)]

    assert runner.invoke(app, args).exit_code == 0
    [rfc] = (repo / "docs" / "rfcs").glob("*.md")
    rfc.write_text("drafted by hand\n", encoding="utf-8")

    again = runner.invoke(app, args)
    assert again.exit_code == 1
    assert "already exists" in again.output
    assert rfc.read_text(encoding="utf-8") == "drafted by hand\n"

    assert runner.invoke(app, [*args, "--force"]).exit_code == 0
    assert rfc.read_text(encoding="utf-8") != "drafted by hand\n"


def _make_repo_with_sources(tmp_path: Path) -> Path:
    repo = tmp_path / "r"
    repo.mkdir()
    write_config(repo, source_roots=["app"])
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

    graph = load_graph(repo)
    node = graph.nodes["composer"]
    assert node.frontmatter.describes == ["app/composer.py"]
    assert node.frontmatter.recommended_tests == ["tests/test_composer.py"]
    assert node.retired_fields == ()

    errors = [f for f in FrontmatterCheck().run(graph) if f.severity.value == "error"]
    assert errors == [], errors


def test_new_component_describes_actually_claims_the_file(tmp_path: Path) -> None:
    repo = _make_repo_with_sources(tmp_path)
    runner.invoke(
        app,
        ["new", "component", "Composer", "--describes", "app/composer.py", "--path", str(repo)],
    )
    graph = load_graph(repo)
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
    graph = load_graph(repo)
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
    graph = load_graph(repo)
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
    write_config(repo, source_roots=["src"])
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


def test_the_no_surface_note_says_what_a_surface_is_once_for_all_the_files(
    tmp_path: Path,
) -> None:
    repo = _make_repo_with_cli_tool(tmp_path)
    for name in ("one", "two"):
        (repo / "src" / f"{name}.py").write_text("def helper() -> int:\n    return 1\n", "utf-8")
    result = runner.invoke(
        app,
        [
            "new",
            "component",
            "Plain",
            "--describes",
            "src/one.py",
            "--describes",
            "src/two.py",
            "--describes",
            "src/tool.py",
            "--from-surface",
            "--path",
            str(repo),
        ],
    )
    assert result.exit_code == 0, result.output

    notes = [line for line in unstyle(result.output).splitlines() if "no derivable" in line]
    assert len(notes) == 1
    assert "src/one.py, src/two.py" in notes[0]
    assert "src/tool.py" not in notes[0]
    assert (
        "a surface is the commands, options, routes, exports or environment variables" in notes[0]
    )


def test_a_new_component_says_what_to_write_and_how_to_tie_it_to_code(tmp_path: Path) -> None:
    repo = _make_repo_with_sources(tmp_path)
    result = runner.invoke(
        app,
        ["new", "component", "Composer", "--describes", "app/composer.py", "--path", str(repo)],
    )
    assert result.exit_code == 0, result.output

    doc = repo / "docs" / "components" / "composer.md"
    [guidance] = re.findall(r"<!-- (Say what the code is for.*?) -->", doc.read_text("utf-8"), re.S)
    for expected in (
        "why it works that way",
        "Class.method",
        "irminsul anchors --suggest",
        "claim:",
    ):
        assert expected in guidance


def test_the_guidance_in_a_new_component_raises_no_finding_of_its_own(tmp_path: Path) -> None:
    """The guidance names an anchor and a claim in prose, so a check that read the comment as
    either would report on every scaffolded doc: the findings are those of the doc without it."""
    repo = _make_repo_with_sources(tmp_path)
    runner.invoke(
        app,
        ["new", "component", "Composer", "--describes", "app/composer.py", "--path", str(repo)],
    )
    doc = repo / "docs" / "components" / "composer.md"
    stable = (
        doc.read_text(encoding="utf-8")
        .replace("status: draft", "status: stable")
        .replace(
            "# summary: one sentence saying what this doc covers; the agent manifest lists it.",
            "summary: Composes.",
        )
        .replace("<!-- Describe what this component does NOT do. -->", "It composes one thing.")
    )
    guidance = re.findall(r"<!-- Say what the code is for.*? -->\n", stable, re.S)
    assert len(guidance) == 1

    def codes(text: str) -> list[str]:
        doc.write_text(text, encoding="utf-8")
        return [
            f["code"] for f in check_findings(repo) if f["path"] == "docs/components/composer.md"
        ]

    assert codes(stable) == codes(stable.replace(guidance[0], ""))


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
    graph = load_graph(repo)
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
    write_config(repo, source_roots=["src"])
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
    graph = load_graph(repo)
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


def test_new_leaves_the_folder_index_alone(tmp_path: Path) -> None:
    """The folder is the list, so a new doc is one edit: the doc itself."""
    repo = _make_repo(tmp_path)
    decisions = repo / "docs" / "decisions"
    decisions.mkdir()
    index = "---\nid: decisions\ntitle: D\nstatus: stable\n---\n\n# D\n"
    (decisions / "INDEX.md").write_text(index, encoding="utf-8")

    result = runner.invoke(app, ["new", "adr", "Foo] bar", "--path", str(repo)])
    assert result.exit_code == 0, result.output

    assert (decisions / "INDEX.md").read_text(encoding="utf-8") == index
    assert (decisions / "foo-bar.md").is_file()


def test_a_template_variable_nobody_passed_is_an_error_not_an_empty_string(
    tmp_path: Path,
) -> None:
    from jinja2 import UndefinedError

    from irminsul.config import IrminsulConfig
    from irminsul.new.command import NewSpec, write_new

    repo = _make_repo(tmp_path)
    spec = NewSpec(kind="component", title="Half filled", extra={"describes": ["a.py"]})

    with pytest.raises(UndefinedError):
        write_new(repo, spec, IrminsulConfig())

    assert not (repo / "docs" / "components" / "half-filled.md").exists()


def test_frontmatter_values_are_yaml_escaped(tmp_path: Path) -> None:
    """The template quoted `describes` values by hand and passed the title through
    `tojson`, which is JSON's idea of a string, not YAML's.

    A quote in a path broke the block; a newline injected whatever keys followed it;
    and `json.dumps` escapes an emoji as a surrogate pair, which YAML cannot parse.
    """

    def metadata(doc: Path) -> dict[str, object]:
        parsed = read_frontmatter(doc.read_text(encoding="utf-8"))
        assert parsed is not None
        return parsed[0]

    repo = _make_repo(tmp_path)
    emoji_title = "Payments " + chr(0x1F4B8) + " service"
    result = runner.invoke(app, ["new", "component", emoji_title, "--path", str(repo)])
    assert result.exit_code == 0, result.output
    doc = repo / "docs" / "components" / "payments-service.md"
    assert metadata(doc)["title"] == emoji_title

    injected = 'app/thing.py"' + chr(10) + "status: stable"
    result = runner.invoke(
        app, ["new", "component", "Injector", "--describes", injected, "--path", str(repo)]
    )
    assert result.exit_code == 0, result.output
    meta = metadata(repo / "docs" / "components" / "injector.md")
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


def _uncommented(text: str) -> str:
    """`text` with each comment's example kept and its opening explanation dropped."""
    out: list[str] = []
    explaining = False
    for line in text.splitlines():
        if line.startswith("<!--"):
            explaining = True
            continue
        if explaining:
            explaining = bool(line.strip())
            continue
        if line.strip() == "-->":
            continue
        out.append(line)
    return "\n".join(out) + "\n"


def test_the_rfc_template_example_follows_the_requirement_grammar(tmp_path: Path) -> None:
    """A template example that the grammar rejects teaches the shape it rejects."""
    from irminsul.checks.requirement_grammar import RequirementGrammarCheck

    repo = _make_repo(tmp_path)
    result = runner.invoke(app, ["new", "rfc", "Export rows", "--path", str(repo)])
    assert result.exit_code == 0, result.output
    doc = repo / "docs" / "rfcs" / "export-rows.md"
    assert "## Requirements" in doc.read_text(encoding="utf-8")
    assert "## Tasks" in doc.read_text(encoding="utf-8")

    doc.write_text(_uncommented(doc.read_text(encoding="utf-8")), encoding="utf-8")
    graph = load_graph(repo)

    assert RequirementGrammarCheck().run(graph) == []
    requirements = graph.requirements["export-rows"].requirements
    assert [requirement.req_id for requirement in requirements] == [
        "export-writes-one-row-per-record"
    ]
    assert [task.task_id for task in graph.tasks["export-rows"].tasks] == ["T1"]


def _scaffolded_rfc_shape(repo: Path, doc_id: str) -> tuple[str | None, list[str]]:
    graph = load_graph(repo)
    headings = [h.text for h in graph.headings[doc_id] if h.level == 2]
    return graph.nodes[doc_id].frontmatter.weight, headings


def test_the_problem_comment_asks_for_plain_words_and_sends_exact_names_to_design_detail(
    tmp_path: Path,
) -> None:
    """The comment asked for "names and numbers", and an example full of commands then drew
    `rfc-structure/dense-paragraph` for four or more code spans."""
    repo = _make_repo(tmp_path)
    result = runner.invoke(app, ["new", "rfc", "Export rows", "--path", str(repo)])
    assert result.exit_code == 0, result.output

    text = (repo / "docs" / "rfcs" / "export-rows.md").read_text(encoding="utf-8")
    problem = " ".join(text.split("## Problem")[1].split("## How it works")[0].split())

    assert "told in plain words" in problem
    assert "Exact commands, file names and ids go under Design detail" in problem


def test_a_new_rfc_is_written_in_two_parts(tmp_path: Path) -> None:
    repo = _make_repo(tmp_path)
    result = runner.invoke(app, ["new", "rfc", "Export rows", "--path", str(repo)])
    assert result.exit_code == 0, result.output

    assert _scaffolded_rfc_shape(repo, "export-rows") == (
        "large",
        [
            "Summary",
            "Problem",
            "How it works",
            "Cost and risk",
            "Decisions",
            "Design detail",
            "Requirements",
            "Tasks",
        ],
    )


def test_a_new_small_rfc_is_written_in_two_parts(tmp_path: Path) -> None:
    repo = _make_repo(tmp_path)
    result = runner.invoke(
        app, ["new", "rfc", "--small", "Exit 1 on an existing baseline", "--path", str(repo)]
    )
    assert result.exit_code == 0, result.output

    assert _scaffolded_rfc_shape(repo, "exit-1-on-an-existing-baseline") == (
        "small",
        ["Summary", "Decisions", "Design detail", "Requirements", "Tasks"],
    )


def test_the_small_rfc_template_example_follows_the_requirement_grammar(tmp_path: Path) -> None:
    from irminsul.checks.requirement_grammar import RequirementGrammarCheck

    repo = _make_repo(tmp_path)
    result = runner.invoke(app, ["new", "rfc", "--small", "Export rows", "--path", str(repo)])
    assert result.exit_code == 0, result.output
    doc = repo / "docs" / "rfcs" / "export-rows.md"

    doc.write_text(_uncommented(doc.read_text(encoding="utf-8")), encoding="utf-8")
    graph = load_graph(repo)

    assert RequirementGrammarCheck().run(graph) == []
    assert [task.task_id for task in graph.tasks["export-rows"].tasks] == ["T1"]


def test_a_scaffolded_rfc_declares_no_requirement_and_no_task(tmp_path: Path) -> None:
    """The template's example sits in a comment, and a comment declares nothing."""
    repo = _make_repo(tmp_path)
    result = runner.invoke(app, ["new", "rfc", "Export rows", "--path", str(repo)])
    assert result.exit_code == 0, result.output

    graph = load_graph(repo)

    assert graph.requirements["export-rows"].requirements == ()
    assert graph.tasks["export-rows"].tasks == ()
