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


def test_broad_glob_with_children_warns(fixture_repo: Callable[[str], Path]) -> None:
    repo = fixture_repo("soft-parent-child")
    findings = _findings(repo)
    warnings = [f for f in findings if f.severity == Severity.warning]
    assert any("wildcard" in f.message for f in warnings)


def test_index_auto_owns_siblings_no_warnings(tmp_path: Path) -> None:
    """INDEX auto-owns all siblings; no warnings are emitted for sibling presence."""
    repo = tmp_path / "r"
    repo.mkdir()
    (repo / "irminsul.toml").write_text(
        'project_name = "r"\n'
        '[paths]\ndocs_root = "docs"\nsource_roots = ["app"]\n'
        '[checks]\nenabled = ["parent-child"]\n',
        encoding="utf-8",
    )
    (repo / "app").mkdir()
    docs = repo / "docs" / "components" / "thing"
    docs.mkdir(parents=True)
    (docs / "INDEX.md").write_text(
        "---\nid: thing\ntitle: Thing\n"
        "status: stable\n"
        "describes: []\n---\n\n# Thing\n\n- [`sibling`](sibling.md) — a sibling\n",
        encoding="utf-8",
    )
    (docs / "sibling.md").write_text(
        "---\nid: sibling\ntitle: Sibling\nstatus: stable\n---\n\n# Sibling\n",
        encoding="utf-8",
    )

    config = load(find_config(repo))
    graph = build_graph(repo, config)
    findings = ParentChildCheck().run(graph)
    warnings = [f for f in findings if f.severity == Severity.warning]
    assert not any("sibling" in f.message for f in warnings)


def test_unlisted_sibling_warns_and_the_fix_links_it(tmp_path: Path) -> None:
    from irminsul.fix import apply_fixes

    repo = tmp_path / "r"
    docs = repo / "docs" / "guides"
    docs.mkdir(parents=True)
    (repo / "irminsul.toml").write_text(
        'project_name = "r"\n[paths]\ndocs_root = "docs"\nsource_roots = []\n', encoding="utf-8"
    )
    (docs / "INDEX.md").write_text(
        "---\nid: guides\ntitle: Guides\nstatus: stable\n---\n\n"
        "# Guides\n\n- [`listed`](listed.md) — listed\n\n## Notes\n\nProse.\n",
        encoding="utf-8",
    )
    for name in ("listed", "missing"):
        (docs / f"{name}.md").write_text(
            f"---\nid: {name}\ntitle: {name}\nstatus: stable\n---\n\n# x\n",
            encoding="utf-8",
        )

    graph = build_graph(repo, load(find_config(repo)))
    check = ParentChildCheck()
    findings = [f for f in check.run(graph) if f.category == "unlisted-sibling"]
    assert [(f.data or {}).get("sibling") for f in findings] == ["missing"]

    fixes = check.fixes(findings, graph)
    assert fixes and all(fix.requires_confirm for fix in fixes)
    apply_fixes(repo, fixes, dry_run=False, confirm=True)
    text = (docs / "INDEX.md").read_text(encoding="utf-8")
    assert text.index("(missing.md)") < text.index("## Notes")
    assert [f for f in _findings(repo) if f.category == "unlisted-sibling"] == []
