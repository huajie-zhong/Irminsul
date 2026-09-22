"""Tests for build_graph()."""

from __future__ import annotations

import sys
from collections.abc import Callable
from pathlib import Path

import pytest

from irminsul.config import load
from irminsul.docgraph import EXEMPT_TOPLEVEL_NAMES, _walk_docs, build_graph


def test_build_graph_good_fixture(fixture_repo: Callable[[str], Path]) -> None:
    repo = fixture_repo("good")
    cfg = load(repo / "irminsul.toml")
    graph = build_graph(repo, cfg)

    assert "composer" in graph.nodes
    assert graph.nodes["composer"].path == Path("docs/components/composer.md")
    assert graph.parse_failures == []
    assert graph.missing_frontmatter == []


def test_build_graph_bad_frontmatter_surfaces_failures(
    fixture_repo: Callable[[str], Path],
) -> None:
    repo = fixture_repo("bad-frontmatter")
    cfg = load(repo / "irminsul.toml")
    graph = build_graph(repo, cfg)

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
    cfg = load(tmp_path / "irminsul.toml")
    graph = build_graph(tmp_path, cfg)
    assert graph.nodes == {}
    assert graph.missing_frontmatter == []
    assert graph.parse_failures == []


def test_build_graph_with_missing_docs_root(tmp_path: Path) -> None:
    (tmp_path / "irminsul.toml").write_text(
        '[paths]\ndocs_root = "docs"\nsource_roots = []\n', encoding="utf-8"
    )
    cfg = load(tmp_path / "irminsul.toml")
    graph = build_graph(tmp_path, cfg)
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
    cfg = load(tmp_path / "irminsul.toml")
    graph = build_graph(tmp_path, cfg)
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
    graph = build_graph(tmp_path, load(tmp_path / "irminsul.toml"))
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
    graph = build_graph(tmp_path, load(tmp_path / "irminsul.toml"))
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
    (repo / "irminsul.toml").write_text(
        'project_name = "r"\n[paths]\ndocs_root = "docs"\nsource_roots = []\n', encoding="utf-8"
    )
    (docs / "one.md").write_text(
        "---\nid: one\ntitle: One\nstatus: stable\n---\n\n# One\n", encoding="utf-8"
    )
    try:
        os.symlink(repo / "docs", docs / "loop", target_is_directory=True)
    except (OSError, NotImplementedError):
        pytest.skip("symlink creation unavailable")

    graph = build_graph(repo, load(repo / "irminsul.toml"))
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
    (repo / "irminsul.toml").write_text(
        'project_name = "r"\n[paths]\ndocs_root = "docs"\nsource_roots = []\n', encoding="utf-8"
    )
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

    graph = build_graph(repo, load(repo / "irminsul.toml"))
    assert sorted(graph.nodes) == ["one"]
