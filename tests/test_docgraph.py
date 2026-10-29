"""Tests for build_graph()."""

from __future__ import annotations

import sys
from collections.abc import Callable
from pathlib import Path

import pytest

from irminsul.docgraph import EXEMPT_TOPLEVEL_NAMES, _walk_docs

from .conftest import load_graph, write_config


def test_build_graph_good_fixture(fixture_repo: Callable[[str], Path]) -> None:
    repo = fixture_repo("good")
    graph = load_graph(repo)

    assert "composer" in graph.nodes
    assert graph.nodes["composer"].path == Path("docs/components/composer.md")
    assert graph.parse_failures == []
    assert graph.missing_frontmatter == []


def test_build_graph_bad_frontmatter_surfaces_failures(
    fixture_repo: Callable[[str], Path],
) -> None:
    repo = fixture_repo("bad-frontmatter")
    graph = load_graph(repo)

    failure_paths = {str(f.path) for f in graph.parse_failures}
    # bad-status and missing-title should both fail validation.
    assert any("bad-status" in p for p in failure_paths)
    assert any("missing-title" in p for p in failure_paths)
    # no-frontmatter is captured separately.
    assert any("no-frontmatter" in str(p) for p in graph.missing_frontmatter)
    # renamed.md parses successfully but with a mismatched id.
    assert "not-renamed" in graph.nodes


def test_build_graph_skips_exempt_toplevel(tmp_path: Path) -> None:
    docs = tmp_path / "docs"
    docs.mkdir()
    for name in EXEMPT_TOPLEVEL_NAMES:
        (docs / name).write_text("# top level\n", encoding="utf-8")
    (tmp_path / "irminsul.toml").write_text(
        '[paths]\ndocs_root = "docs"\nsource_roots = []\n', encoding="utf-8"
    )
    graph = load_graph(tmp_path)
    assert graph.nodes == {}
    assert graph.missing_frontmatter == []
    assert graph.parse_failures == []


def test_build_graph_with_missing_docs_root(tmp_path: Path) -> None:
    (tmp_path / "irminsul.toml").write_text(
        '[paths]\ndocs_root = "docs"\nsource_roots = []\n', encoding="utf-8"
    )
    graph = load_graph(tmp_path)
    assert graph.nodes == {}


def test_build_graph_skips_harness_files_when_docs_root_is_the_repo_root(
    tmp_path: Path,
) -> None:
    """`irminsul init` writes `CLAUDE.md` and `.claude/skills/irminsul/SKILL.md`
    at the repo root. With `docs_root = "."` neither may become a graph node,
    since neither carries doc frontmatter."""
    (tmp_path / "CLAUDE.md").write_text("@AGENTS.md\n", encoding="utf-8")
    skill = tmp_path / ".claude" / "skills" / "irminsul" / "SKILL.md"
    skill.parent.mkdir(parents=True)
    skill.write_text("---\nname: irminsul\n---\n", encoding="utf-8")
    (tmp_path / "irminsul.toml").write_text(
        '[paths]\ndocs_root = "."\nsource_roots = []\n', encoding="utf-8"
    )
    graph = load_graph(tmp_path)
    assert graph.nodes == {}
    assert graph.missing_frontmatter == []
    assert graph.parse_failures == []


def _doc_with_frontmatter(lead: str) -> str:
    return (
        "---\n"
        "id: widget\n"
        "title: Widget\n"
        ""
        "status: stable\n"
        "describes: []\n"
        "---\n" + lead + "# Widget\n\nprose\n"
    )


def test_body_offset_maps_body_lines_back_to_file_lines(tmp_path: Path) -> None:
    doc = tmp_path / "docs" / "components" / "widget.md"
    doc.parent.mkdir(parents=True)
    doc.write_text(_doc_with_frontmatter("\n"), encoding="utf-8")
    (tmp_path / "irminsul.toml").write_text(
        '[paths]\ndocs_root = "docs"\nsource_roots = []\n', encoding="utf-8"
    )
    graph = load_graph(tmp_path)
    node = graph.nodes["widget"]

    file_lines = doc.read_text(encoding="utf-8").splitlines()
    for body_line, text in enumerate(node.body.splitlines(), start=1):
        assert file_lines[node.file_line(body_line) - 1] == text


def test_body_offset_absorbs_extra_blank_lines_after_frontmatter(tmp_path: Path) -> None:
    doc = tmp_path / "docs" / "components" / "widget.md"
    doc.parent.mkdir(parents=True)
    doc.write_text(_doc_with_frontmatter("\n\n\n"), encoding="utf-8")
    (tmp_path / "irminsul.toml").write_text(
        '[paths]\ndocs_root = "docs"\nsource_roots = []\n', encoding="utf-8"
    )
    graph = load_graph(tmp_path)
    node = graph.nodes["widget"]

    file_lines = doc.read_text(encoding="utf-8").splitlines()
    assert file_lines[node.file_line(1) - 1] == "# Widget"
    for body_line, text in enumerate(node.body.splitlines(), start=1):
        assert file_lines[node.file_line(body_line) - 1] == text


def test_the_doc_walk_does_not_follow_a_directory_symlink(tmp_path: Path) -> None:
    """A junction pointing at an ancestor was walked until the paths grew too long."""
    import os

    repo = tmp_path / "r"
    docs = repo / "docs" / "components"
    docs.mkdir(parents=True)
    write_config(repo)
    (docs / "one.md").write_text(
        "---\nid: one\ntitle: One\nstatus: stable\n---\n\n# One\n", encoding="utf-8"
    )
    try:
        os.symlink(repo / "docs", docs / "loop", target_is_directory=True)
    except (OSError, NotImplementedError):
        pytest.skip("symlink creation unavailable")

    graph = load_graph(repo)
    assert sorted(graph.nodes) == ["one"]


def test_the_doc_walk_does_not_follow_a_directory_junction(tmp_path: Path) -> None:
    """The symlink test above skips on Windows, where the loop is a junction instead.

    A junction needs no Developer Mode, so a workspace can hold one unnoticed, and
    `Path.is_symlink()` reports False for it.
    """
    import subprocess

    if sys.platform != "win32":
        pytest.skip("directory junctions are a Windows concept")

    repo = tmp_path / "r"
    docs = repo / "docs" / "components"
    docs.mkdir(parents=True)
    write_config(repo)
    (docs / "one.md").write_text(
        "---\nid: one\ntitle: One\nstatus: stable\n---\n\n# One\n", encoding="utf-8"
    )
    result = subprocess.run(
        ["cmd", "/c", "mklink", "/J", str(docs / "loop"), str(repo / "docs")],
        capture_output=True,
        check=False,
    )
    if result.returncode != 0:
        pytest.skip("junction creation unavailable")

    # The walk itself, not the graph: `nodes` is keyed by doc id, so re-walking the
    # same file through the loop collapses back to one entry and hides the descent.
    assert _walk_docs(repo / "docs") == [docs / "one.md"]

    graph = load_graph(repo)
    assert sorted(graph.nodes) == ["one"]


def test_a_run_parses_each_doc_body_once(
    fixture_repo: Callable[[str], Path], monkeypatch: pytest.MonkeyPatch
) -> None:
    """Every reader of a body's markdown reads `DocNode.tokens`. One that parsed for itself
    would parse some body twice, which is the regression this guards."""
    from markdown_it import MarkdownIt

    from irminsul.checks.base import fix_commands
    from irminsul.checks.pipeline import run_checks

    parsed: list[str] = []
    real_parse = MarkdownIt.parse

    def counted(self: MarkdownIt, src: str, env: object = None) -> object:
        parsed.append(src)
        return real_parse(self, src, env)

    monkeypatch.setattr(MarkdownIt, "parse", counted)
    graph = load_graph(fixture_repo("soft-glossary"))
    result = run_checks(graph, baseline=False)
    fix_commands(result.findings, graph)

    bodies = [node.body for node in graph.nodes.values()]
    assert bodies and all(parsed.count(body) == 1 for body in bodies)


def test_a_run_resolves_ownership_claims_once(
    fixture_repo: Callable[[str], Path], monkeypatch: pytest.MonkeyPatch
) -> None:
    """`uniqueness` and `import-deps` both ask who owns each file; they read one table."""
    import irminsul.checks.uniqueness as uniqueness
    from irminsul.checks.pipeline import run_checks

    calls = 0
    real = uniqueness.resolve_claims

    def counted(*args: object, **kwargs: object) -> object:
        nonlocal calls
        calls += 1
        return real(*args, **kwargs)

    monkeypatch.setattr(uniqueness, "resolve_claims", counted)
    graph = load_graph(fixture_repo("bad-dependency"))
    run_checks(graph, only=["uniqueness", "import-deps"], baseline=False)

    assert calls == 1
    assert graph.claims is graph.claims


def test_resolve_doc_target_accepts_an_absolute_path(
    fixture_repo: Callable[[str], Path],
) -> None:
    from irminsul.docgraph import resolve_doc_target

    repo = fixture_repo("soft-orphans")
    graph = load_graph(repo)

    absolute = repo / "docs" / "components" / "hub.md"
    assert resolve_doc_target(graph, str(absolute)) == "docs/components/hub.md"
    assert resolve_doc_target(graph, "docs/components/hub.md") == "docs/components/hub.md"
    assert resolve_doc_target(graph, "hub") == "docs/components/hub.md"
    assert resolve_doc_target(graph, str(repo.parent / "elsewhere.md")) is None


def test_a_run_reads_each_guidance_file_once(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import irminsul.docgraph as docgraph
    from irminsul.checks.pipeline import run_checks

    write_config(tmp_path)
    (tmp_path / "README.md").write_text("# Tool\n\nSee [it](#tool).\n", encoding="utf-8")
    calls = 0
    real = docgraph.read_guidance

    def counted(*args: object, **kwargs: object) -> object:
        nonlocal calls
        calls += 1
        return real(*args, **kwargs)  # type: ignore[arg-type]

    monkeypatch.setattr(docgraph, "read_guidance", counted)
    graph = load_graph(tmp_path)
    run_checks(graph, only=["links", "retired-references", "code-references"], baseline=False)

    assert calls == 1
    assert graph.guidance_files is graph.guidance_files


def test_a_guidance_file_carries_its_links_and_why_it_would_not_read(tmp_path: Path) -> None:
    write_config(tmp_path)
    (tmp_path / "README.md").write_text("# Tool\n\n[a](#tool) [b](docs/x.md#y)\n", encoding="utf-8")
    (tmp_path / "AGENTS.md").write_bytes(b"\xff\xfe\x00 not utf-8")

    guidance = {g.display: g for g in load_graph(tmp_path).guidance_files}

    assert sorted(guidance) == ["AGENTS.md", "README.md"]
    assert guidance["AGENTS.md"].text is None
    assert (guidance["AGENTS.md"].unreadable or "").startswith("UnicodeDecodeError")
    readme = guidance["README.md"]
    assert readme.unreadable is None and readme.root == ""
    assert [(link.href, link.line, link.target, link.anchor) for link in readme.links] == [
        ("#tool", 3, "", "tool"),
        ("docs/x.md#y", 3, "docs/x.md", "y"),
    ]
