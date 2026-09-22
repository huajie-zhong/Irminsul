"""Source-policy behavior in derived change footprints."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from irminsul.change.footprint import touched_components
from irminsul.config import IrminsulConfig, Paths
from irminsul.docgraph import build_graph


def _config(*, excludes: list[str] | None = None) -> IrminsulConfig:
    return IrminsulConfig(
        project_name="footprint-policy",
        paths=Paths(
            docs_root="docs",
            source_roots=["app"],
            source_excludes=excludes or [],
        ),
    )


def test_deleted_explicitly_excluded_path_is_not_source(
    fixture_repo: Callable[[str], Path],
) -> None:
    repo = fixture_repo("good")
    config = _config(excludes=["app/composer.py"])
    graph = build_graph(repo, config)
    (repo / "app" / "composer.py").unlink()

    footprint = touched_components(graph, config, frozenset({"app/composer.py"}))

    assert footprint.touched == {}
    assert footprint.unowned_source == ()


def test_deleted_gitignored_path_is_not_source(
    fixture_repo: Callable[[str], Path],
) -> None:
    repo = fixture_repo("good")
    (repo / "app" / ".gitignore").write_text("composer.py\n", encoding="utf-8")
    config = _config()
    graph = build_graph(repo, config)
    (repo / "app" / "composer.py").unlink()

    footprint = touched_components(graph, config, frozenset({"app/composer.py"}))

    assert footprint.touched == {}
    assert footprint.unowned_source == ()


def test_deleted_included_path_keeps_its_owner(
    fixture_repo: Callable[[str], Path],
) -> None:
    repo = fixture_repo("good")
    config = _config()
    graph = build_graph(repo, config)
    (repo / "app" / "composer.py").unlink()

    footprint = touched_components(graph, config, frozenset({"app/composer.py"}))

    assert footprint.touched == {"composer": ("app/composer.py",)}
    assert footprint.unowned_source == ()
