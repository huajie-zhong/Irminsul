"""Tests for build_graph()."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from irminsul.config import load
from irminsul.docgraph import EXEMPT_TOPLEVEL_NAMES, build_graph


def test_build_graph_good_fixture(fixture_repo: Callable[[str], Path]) -> None:
    repo = fixture_repo("good")
    cfg = load(repo / "irminsul.toml")
    graph = build_graph(repo, cfg)

    assert "composer" in graph.nodes
    assert graph.nodes["composer"].path == Path("docs/20-components/composer.md")
    assert graph.parse_failures == []
    assert graph.missing_frontmatter == []


def test_build_graph_bad_frontmatter_surfaces_failures(
    fixture_repo: Callable[[str], Path],
) -> None:
    repo = fixture_repo("bad-frontmatter")
    cfg = load(repo / "irminsul.toml")
    graph = build_graph(repo, cfg)

    failure_paths = {str(f.path) for f in graph.parse_failures}
    # bad-tier and missing-audience should both fail validation.
    assert any("bad-tier" in p for p in failure_paths)
    assert any("missing-audience" in p for p in failure_paths)
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
