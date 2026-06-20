"""Tests for inventory fingerprint re-pin (RFC 0027 freshness)."""

from __future__ import annotations

from pathlib import Path

import frontmatter as pyfm

from irminsul.checks.globs import walk_source_files
from irminsul.config import load
from irminsul.docgraph import build_graph
from irminsul.frontmatter import DocFrontmatter
from irminsul.inventory.fingerprint import (
    current_hash,
    extract_surface,
    repin_node,
    set_fingerprints,
)

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

DOC = """\
---
id: cli
title: CLI
audience: explanation
tier: 3
status: stable
describes: [src/cli.py]
inventory:
  - kind: cli
    source: src/cli.py
    complete: true
    items: [alpha]
    omit: [beta]
    fingerprints:
      alpha: stale0000000
---

# CLI

Body.
"""


def _repo(tmp_path: Path) -> Path:
    repo = tmp_path / "r"
    (repo / "src").mkdir(parents=True)
    (repo / "irminsul.toml").write_text(
        'project_name = "r"\n[paths]\ndocs_root = "docs"\nsource_roots = ["src"]\n',
        encoding="utf-8",
    )
    (repo / "src" / "cli.py").write_text(CLI_SRC, encoding="utf-8")
    doc = repo / "docs" / "20-components" / "cli.md"
    doc.parent.mkdir(parents=True, exist_ok=True)
    doc.write_text(DOC, encoding="utf-8")
    return repo


def _alpha_hash(repo: Path) -> str:
    config = load(repo / "irminsul.toml")
    source_files, _ = walk_source_files(repo, config.paths.source_roots)
    surface = extract_surface(config, source_files, "cli", ["src/cli.py"])
    digest = current_hash(repo, surface["alpha"])
    assert digest is not None
    return digest


def test_set_fingerprints_idempotent() -> None:
    same = set_fingerprints(DOC, "cli", "src/cli.py", {"alpha": "stale0000000"})
    assert same == DOC


def test_set_fingerprints_rewrites_value() -> None:
    out = set_fingerprints(DOC, "cli", "src/cli.py", {"alpha": "fresh1111111"})
    assert "fresh1111111" in out
    assert "stale0000000" not in out
    assert out.endswith("# CLI\n\nBody.\n")  # body preserved


def test_set_fingerprints_no_matching_entry_is_noop() -> None:
    assert set_fingerprints(DOC, "http", "src/cli.py", {"x": "y"}) == DOC


def test_repin_node_refreshes_to_live_hash(tmp_path: Path) -> None:
    repo = _repo(tmp_path)
    config = load(repo / "irminsul.toml")
    source_files, _ = walk_source_files(repo, config.paths.source_roots)
    graph = build_graph(repo, config)
    node = next(n for n in graph.nodes.values() if n.id == "cli")

    text = (repo / node.path).read_text(encoding="utf-8")
    new_text, refreshed = repin_node(repo, config, source_files, node.frontmatter, text)

    assert refreshed == 1
    assert _alpha_hash(repo) in new_text
    assert "stale0000000" not in new_text

    # Re-pinning the already-fresh text (its frontmatter now holds the live hash)
    # refreshes nothing and leaves the text byte-for-byte unchanged.
    fresh_text, again = repin_node(repo, config, source_files, _parsed_fm(new_text), new_text)
    assert again == 0
    assert fresh_text == new_text


def _parsed_fm(text: str) -> DocFrontmatter:
    return DocFrontmatter.model_validate(dict(pyfm.loads(text).metadata))
