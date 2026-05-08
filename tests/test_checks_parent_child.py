"""Tests for ParentChildCheck."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from irminsul.checks.base import Severity
from irminsul.checks.parent_child import ParentChildCheck
from irminsul.config import find_config, load
from irminsul.docgraph import build_graph


def _findings(repo: Path) -> list:
    config = load(find_config(repo))
    graph = build_graph(repo, config)
    return ParentChildCheck().run(graph)


def test_unknown_child_id_errors(fixture_repo: Callable[[str], Path]) -> None:
    repo = fixture_repo("soft-parent-child")
    findings = _findings(repo)
    errors = [f for f in findings if f.severity == Severity.error]
    assert any("widget-bogus" in f.message for f in errors)


def test_unlisted_sibling_warned(fixture_repo: Callable[[str], Path]) -> None:
    repo = fixture_repo("soft-parent-child")
    findings = _findings(repo)
    warnings = [f for f in findings if f.severity == Severity.warning]
    assert any("widget-extra" in f.message for f in warnings)


def test_broad_glob_with_children_errors(fixture_repo: Callable[[str], Path]) -> None:
    repo = fixture_repo("soft-parent-child")
    findings = _findings(repo)
    errors = [f for f in findings if f.severity == Severity.error]
    assert any("wildcard" in f.message for f in errors)


def test_index_without_children_skipped(tmp_path: Path) -> None:
    """An INDEX with empty children:[] shouldn't get flagged for asymmetry."""
    repo = tmp_path / "r"
    repo.mkdir()
    (repo / "irminsul.toml").write_text(
        'project_name = "r"\n'
        '[paths]\ndocs_root = "docs"\nsource_roots = ["app"]\n'
        '[checks]\nsoft_deterministic = ["parent-child"]\n',
        encoding="utf-8",
    )
    (repo / "app").mkdir()
    docs = repo / "docs" / "20-components" / "thing"
    docs.mkdir(parents=True)
    (docs / "INDEX.md").write_text(
        "---\nid: thing\ntitle: Thing\naudience: reference\ntier: 3\n"
        'status: stable\nowner: "@a"\nlast_reviewed: 2026-05-08\n'
        "describes: []\n---\n\n# Thing\n",
        encoding="utf-8",
    )
    (docs / "sibling.md").write_text(
        "---\nid: sibling\ntitle: Sibling\naudience: reference\ntier: 3\n"
        'status: stable\nowner: "@a"\nlast_reviewed: 2026-05-08\n'
        "---\n\n# Sibling\n",
        encoding="utf-8",
    )

    config = load(find_config(repo))
    graph = build_graph(repo, config)
    findings = ParentChildCheck().run(graph)
    # No declared children -> we don't flag the unlisted sibling.
    warnings = [f for f in findings if f.severity == Severity.warning]
    assert not any("sibling" in f.message for f in warnings)
