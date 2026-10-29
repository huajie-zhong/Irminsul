"""Tests for `SourceTree`, the graph's snapshot of the configured source."""

from __future__ import annotations

import ast
import dataclasses
from pathlib import Path
from typing import Any

import pytest

import irminsul.checks.globs as globs
from irminsul.docgraph import DocGraph

from .conftest import config_toml, load_graph, write, write_config


def _repo(tmp_path: Path, *, test_roots: bool) -> Path:
    # With no `enabled`, `extra` lands inside the `[paths]` table.
    write_config(
        tmp_path, source_roots=["src"], extra='test_roots = ["tests"]\n' if test_roots else ""
    )
    write(tmp_path, "src/a.py", "def a() -> None:\n    pass\n")
    write(tmp_path, "tests/test_a.py", "def test_a() -> None:\n    pass\n")
    write(tmp_path, "docs/components/a.md", "---\nid: a\ntitle: A\nstatus: stable\n---\n# A\n")
    return tmp_path


def test_a_graph_derives_its_source_once(tmp_path: Path) -> None:
    graph = load_graph(_repo(tmp_path, test_roots=True))

    assert graph.source is graph.source
    assert graph.source.walk is graph.source.walk
    assert graph.source.test_walk is graph.source.test_walk


def test_the_walk_is_a_snapshot_and_the_next_graph_reads_again(tmp_path: Path) -> None:
    repo = _repo(tmp_path, test_roots=False)
    graph = load_graph(repo)
    before = [display for _, display in graph.source.files]

    write(repo, "src/b.py", "def b() -> None:\n    pass\n")

    assert [display for _, display in graph.source.files] == before == ["src/a.py"]
    assert [display for _, display in load_graph(repo).source.files] == ["src/a.py", "src/b.py"]


def test_replacing_a_graph_does_not_carry_its_snapshot(tmp_path: Path) -> None:
    graph = load_graph(_repo(tmp_path, test_roots=False))
    first = graph.source

    assert dataclasses.replace(graph).source is not first


def test_the_test_walk_reads_only_the_declared_test_roots(tmp_path: Path) -> None:
    declared = load_graph(_repo(tmp_path / "declared", test_roots=True))
    undeclared = load_graph(_repo(tmp_path / "undeclared", test_roots=False))

    assert [display for _, display in declared.source.test_walk.files] == ["tests/test_a.py"]
    assert undeclared.source.test_walk.files == []
    assert undeclared.source.test_walk.missing_roots == []


def test_a_graph_without_a_repository_has_no_source_tree() -> None:
    with pytest.raises(ValueError, match="no source tree"):
        _ = DocGraph().source


_APP = """import typer

from pkg import helpers

app = typer.Typer()


@app.command()
def serve(port: int = typer.Option(8000, "--port")) -> None:
    helpers.start(port)
"""

_HELPERS = """import os

LIMIT = 5


def start(port: int) -> None:
    os.environ.get("APP_TOKEN")
"""

_DOC = """---
id: app
title: App
status: stable
summary: The app.
describes:
  - src/pkg/*.py
owns_tests:
  - tests/test_app.py
inventory:
  - kind: cli
    items:
      - serve
---

# App

`serve --port` calls `start()` and reads `APP_TOKEN` under `LIMIT`.
<!-- anchor: src/pkg/helpers.py#start -->
"""


def test_a_run_walks_each_scope_once_and_parses_each_file_once(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Every check reads the graph's source tree. One that walked or parsed for itself
    would push these counts up, which is the regression this guards."""
    from irminsul.checks import REGISTRY
    from irminsul.checks.pipeline import run_checks

    config = config_toml(source_roots=["src"], enabled=sorted(REGISTRY))
    write(
        tmp_path, "irminsul.toml", config.replace("[checks]", 'test_roots = ["tests"]\n[checks]', 1)
    )
    write(tmp_path, "src/pkg/__init__.py", "")
    write(tmp_path, "src/pkg/app.py", _APP)
    write(tmp_path, "src/pkg/helpers.py", _HELPERS)
    write(tmp_path, "tests/test_app.py", "def test_app() -> None:\n    pass\n")
    write(tmp_path, "docs/components/app.md", _DOC)
    graph = load_graph(tmp_path)

    walks: list[list[str]] = []
    real_walk = globs._walk_source_files

    def counted_walk(repo_root: Path, source_roots: list[str], **kwargs: Any) -> Any:
        walks.append(list(source_roots))
        return real_walk(repo_root, source_roots, **kwargs)

    parsed: list[str] = []
    real_parse = ast.parse

    def counted_parse(source: Any, *args: Any, **kwargs: Any) -> Any:
        parsed.append(source if isinstance(source, str) else "")
        return real_parse(source, *args, **kwargs)

    monkeypatch.setattr(globs, "_walk_source_files", counted_walk)
    monkeypatch.setattr(ast, "parse", counted_parse)
    run_checks(graph)

    assert sorted(walks) == [["src"], ["tests"]]
    assert sorted(parsed) == sorted(["", _APP, _HELPERS])
