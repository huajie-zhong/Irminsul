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


def _repo(
    tmp_path: Path,
    *,
    items: list[str],
    source: str | None = "src/cli.py",
    complete: bool = False,
    omit: list[str] | None = None,
    fingerprints: dict[str, str] | None = None,
    cli_src: str = CLI_SRC,
) -> Path:
    repo = tmp_path / "r"
    (repo / "src").mkdir(parents=True)
    (repo / "irminsul.toml").write_text(
        'project_name = "r"\n[paths]\ndocs_root = "docs"\nsource_roots = ["src"]\n',
        encoding="utf-8",
    )
    (repo / "src" / "cli.py").write_text(cli_src, encoding="utf-8")
    fm = ["inventory:", "  - kind: cli"]
    if source is not None:
        fm.append(f"    source: {source}")
    if complete:
        fm.append("    complete: true")
    fm.append("    items: [" + ", ".join(items) + "]")
    if omit is not None:
        fm.append("    omit: [" + ", ".join(omit) + "]")
    if fingerprints is not None:
        fm.append("    fingerprints:")
        fm.extend(f"      {ident}: {digest}" for ident, digest in fingerprints.items())
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


# --- Watched surfaces (RFC 0027) ---------------------------------------------


def _alpha_hash(repo: Path) -> str:
    from irminsul.checks.globs import walk_source_files
    from irminsul.inventory.fingerprint import current_hash, extract_surface

    config = load(repo / "irminsul.toml")
    source_files, _ = walk_source_files(repo, config.paths.source_roots)
    surface = extract_surface(config, source_files, "cli", ["src/cli.py"])
    digest = current_hash(repo, surface["alpha"])
    assert digest is not None
    return digest


def test_complete_flags_new_uncovered(tmp_path: Path) -> None:
    findings = _run(_repo(tmp_path, items=["alpha"], complete=True))
    assert all(f.severity == Severity.warning for f in findings)
    assert any("beta" in f.message and "neither lists nor omits" in f.message for f in findings)
    assert not any("alpha" in f.message for f in findings)


def test_complete_with_omit_is_clean(tmp_path: Path) -> None:
    assert _run(_repo(tmp_path, items=["alpha"], complete=True, omit=["beta"])) == []


def test_completeness_off_by_default(tmp_path: Path) -> None:
    # Without `complete`, an uncovered live command is never flagged (RFC 0020 default).
    assert _run(_repo(tmp_path, items=["alpha"])) == []


def test_rotted_omit_flagged(tmp_path: Path) -> None:
    findings = _run(_repo(tmp_path, items=["alpha"], complete=True, omit=["beta", "ghost"]))
    assert any("ghost" in f.message and "not in the live surface" in f.message for f in findings)


def test_fingerprint_match_is_clean(tmp_path: Path) -> None:
    digest = _alpha_hash(_repo(tmp_path / "h", items=["alpha"]))
    repo = _repo(
        tmp_path / "r",
        items=["alpha"],
        complete=True,
        omit=["beta"],
        fingerprints={"alpha": digest},
    )
    assert _run(repo) == []


def test_fingerprint_mismatch_flagged(tmp_path: Path) -> None:
    repo = _repo(
        tmp_path,
        items=["alpha"],
        complete=True,
        omit=["beta"],
        fingerprints={"alpha": "deadbeef0000"},
    )
    findings = _run(repo)
    assert any(
        "alpha" in f.message and "changed" in f.message and f.severity == Severity.warning
        for f in findings
    )
