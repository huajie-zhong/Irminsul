"""Tests for InventoryDriftCheck.fixes (RFC 0022 item 3)."""

from __future__ import annotations

from pathlib import Path

from irminsul.checks.inventory_drift import InventoryDriftCheck
from irminsul.config import load
from irminsul.docgraph import build_graph
from irminsul.fix import apply_fixes

CLI_SRC = """\
import typer

app = typer.Typer()


@app.command()
def alpha():
    pass
"""


def _repo(tmp_path: Path, *, items: list[str]) -> Path:
    repo = tmp_path / "r"
    (repo / "src").mkdir(parents=True)
    (repo / "irminsul.toml").write_text(
        'project_name = "r"\n[paths]\ndocs_root = "docs"\nsource_roots = ["src"]\n',
        encoding="utf-8",
    )
    (repo / "src" / "cli.py").write_text(CLI_SRC, encoding="utf-8")
    doc = repo / "docs" / "20-components" / "cli.md"
    doc.parent.mkdir(parents=True, exist_ok=True)
    doc.write_text(
        "\n".join(
            [
                "---",
                "id: cli",
                "title: CLI",
                "audience: explanation",
                "tier: 3",
                "status: stable",
                "describes: [src/cli.py]",
                "inventory:",
                "  - kind: cli",
                "    source: src/cli.py",
                "    items: [" + ", ".join(items) + "]",
                "---",
                "",
                "# CLI",
                "",
                "Body.",
            ]
        ),
        encoding="utf-8",
    )
    return repo


def _fixes_for(repo: Path) -> tuple[InventoryDriftCheck, list, object]:
    graph = build_graph(repo, load(repo / "irminsul.toml"))
    check = InventoryDriftCheck()
    findings = check.run(graph)
    return check, check.fixes(findings, graph), graph


def test_drifted_item_fix_requires_confirm(tmp_path: Path) -> None:
    repo = _repo(tmp_path, items=["alpha", "ghost"])
    _check, fixes, _graph = _fixes_for(repo)
    assert len(fixes) == 1
    assert fixes[0].requires_confirm is True

    # Held without confirm: file untouched.
    doc = repo / "docs" / "20-components" / "cli.md"
    before = doc.read_text(encoding="utf-8")
    apply_fixes(repo, fixes, dry_run=False, confirm=False)
    assert doc.read_text(encoding="utf-8") == before


def test_drifted_item_pruned_on_confirm(tmp_path: Path) -> None:
    repo = _repo(tmp_path, items=["alpha", "ghost"])
    _check, fixes, _graph = _fixes_for(repo)
    apply_fixes(repo, fixes, dry_run=False, confirm=True)

    text = (repo / "docs" / "20-components" / "cli.md").read_text(encoding="utf-8")
    assert "alpha" in text
    assert "ghost" not in text


def test_no_fix_when_inventory_matches_code(tmp_path: Path) -> None:
    repo = _repo(tmp_path, items=["alpha"])
    _check, fixes, _graph = _fixes_for(repo)
    assert fixes == []
