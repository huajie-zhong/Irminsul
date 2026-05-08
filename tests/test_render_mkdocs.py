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
