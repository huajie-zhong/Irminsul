"""Tests for InventoryDriftCheck (RFC 0020, Rule 1 / anti-lie only)."""

from __future__ import annotations

from pathlib import Path

from irminsul.checks.base import Severity
from irminsul.checks.inventory_drift import InventoryDriftCheck
from irminsul.config import load
from irminsul.docgraph import build_graph

CLI_SRC = """\
import typer

app = typer.Typer()


@app.command()
def alpha():
    pass


@app.command()
def beta():
    pass
"""


def _repo(tmp_path: Path, *, items: list[str], source: str | None = "src/cli.py") -> Path:
    repo = tmp_path / "r"
    (repo / "src").mkdir(parents=True)
    (repo / "irminsul.toml").write_text(
        'project_name = "r"\n[paths]\ndocs_root = "docs"\nsource_roots = ["src"]\n',
        encoding="utf-8",
    )
    (repo / "src" / "cli.py").write_text(CLI_SRC, encoding="utf-8")
    fm = ["inventory:", "  - kind: cli"]
    if source is not None:
        fm.append(f"    source: {source}")
    fm.append("    items: [" + ", ".join(items) + "]")
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
                *fm,
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


def _run(repo: Path) -> list:
    return InventoryDriftCheck().run(build_graph(repo, load(repo / "irminsul.toml")))


def test_declared_missing_item_flagged(tmp_path: Path) -> None:
    findings = _run(_repo(tmp_path, items=["alpha", "ghost"]))
    assert len(findings) == 1
    assert findings[0].severity == Severity.warning
    assert "ghost" in findings[0].message


def test_subset_of_real_items_is_clean(tmp_path: Path) -> None:
    # Only one of two real commands is listed — a curated subset, never flagged.
    assert _run(_repo(tmp_path, items=["alpha"])) == []


def test_no_inventory_is_silent(tmp_path: Path) -> None:
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
        "---\nid: cli\ntitle: CLI\naudience: explanation\ntier: 3\nstatus: stable\n"
        "describes: [src/cli.py]\n---\n\n# CLI\n",
        encoding="utf-8",
    )
    assert _run(repo) == []


def test_source_defaults_to_describes(tmp_path: Path) -> None:
    # No explicit source; falls back to the doc's describes glob (src/cli.py).
    findings = _run(_repo(tmp_path, items=["alpha", "ghost"], source=None))
    assert any("ghost" in f.message for f in findings)
