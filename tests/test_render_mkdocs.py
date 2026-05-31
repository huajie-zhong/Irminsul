"""Tests for the MkDocs renderer.

Skipped when MkDocs isn't installed; we don't want CI matrix legs that lack the
optional `[mkdocs]` extra to fail.
"""

from __future__ import annotations

import importlib.util
from collections.abc import Callable
from pathlib import Path

import pytest

from irminsul.config import load
from irminsul.docgraph import build_graph
from irminsul.render.mkdocs import MkDocsRenderer


@pytest.mark.skipif(importlib.util.find_spec("mkdocs") is None, reason="mkdocs not installed")
def test_render_good_fixture_produces_index(
    tmp_path: Path, fixture_repo: Callable[[str], Path]
) -> None:
    repo = fixture_repo("good")
    cfg = load(repo / "irminsul.toml")
    graph = build_graph(repo, cfg)

    out = tmp_path / "site"
    MkDocsRenderer().build(graph, out)

    # MkDocs may put generated pages under per-doc subdirs; assert at least
    # one html file made it through and the mkdocs.yml was written.
    html_files = list(out.rglob("*.html"))
    assert html_files, f"no html output under {out}"
    assert (repo / "mkdocs.yml").is_file()


def test_long_nav_title_produces_valid_yaml(tmp_path: Path) -> None:
    """A long nav title must not fold mid-string and break mkdocs.yml parsing."""
    from ruamel.yaml import YAML

    repo = tmp_path / "r"
    (repo / "src").mkdir(parents=True)
    (repo / "irminsul.toml").write_text(
        'project_name = "r"\n[paths]\ndocs_root = "docs"\nsource_roots = ["src"]\n',
        encoding="utf-8",
    )
    long_title = "Derive, don't materialize — surfaces, curated inventory, and the boundary lint"
    doc = repo / "docs" / "20-components" / "c.md"
    doc.parent.mkdir(parents=True)
    doc.write_text(
        f"---\nid: c\ntitle: {long_title}\naudience: explanation\ntier: 3\n"
        "status: stable\ndescribes: []\n---\n\n# C\n",
        encoding="utf-8",
    )

    graph = build_graph(repo, load(repo / "irminsul.toml"))
    config_path = repo / "mkdocs.yml"
    MkDocsRenderer()._write_config(graph, config_path)

    # Parses without error, and the long title survives as a single nav key.
    data = YAML(typ="safe").load(config_path.read_text(encoding="utf-8"))
    titles: set[str] = set()

    def _walk(node: object) -> None:
        if isinstance(node, dict):
            for key, value in node.items():
                titles.add(key)
                _walk(value)
        elif isinstance(node, list):
            for item in node:
                _walk(item)

    _walk(data["nav"])
    assert long_title in titles


def test_render_without_mkdocs_raises(
    tmp_path: Path, fixture_repo: Callable[[str], Path], monkeypatch: pytest.MonkeyPatch
) -> None:
    """If mkdocs isn't on PATH, the renderer raises a clear error instead of crashing."""
    repo = fixture_repo("good")
    cfg = load(repo / "irminsul.toml")
    graph = build_graph(repo, cfg)

    # Pretend mkdocs isn't installed regardless of the env.
    monkeypatch.setattr("irminsul.render.mkdocs.importlib.util.find_spec", lambda _: None)

    from irminsul.render.mkdocs import MkDocsRenderError

    with pytest.raises(MkDocsRenderError, match="not installed"):
        MkDocsRenderer().build(graph, tmp_path / "site")
