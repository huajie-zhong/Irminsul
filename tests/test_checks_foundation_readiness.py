"""Tests for the foundation-readiness check."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from irminsul.checks.foundation_readiness import FoundationReadinessCheck
from irminsul.config import find_config, load
from irminsul.docgraph import build_graph


def _flagged_ids(repo: Path) -> set[str]:
    config = load(find_config(repo))
    graph = build_graph(repo, config)
    return {f.doc_id for f in FoundationReadinessCheck().run(graph)}


def test_scaffold_placeholders_flagged(fixture_repo: Callable[[str], Path]) -> None:
    repo = fixture_repo("soft-foundation-fresh")
    flagged = _flagged_ids(repo)
    assert "principles" in flagged
    assert "overview" in flagged


def test_scaffold_placeholders_flagged_when_docs_root_is_repo_root(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    (repo / "00-foundation").mkdir(parents=True)
    (repo / "10-architecture").mkdir()
    (repo / "irminsul.toml").write_text(
        'project_name = "root-docs"\n[paths]\ndocs_root = "."\nsource_roots = []\n',
        encoding="utf-8",
    )
    (repo / "00-foundation" / "principles.md").write_text(
        """---
id: principles
title: Principles
audience: explanation
tier: 2
status: draft
---

# Principles

Replace this paragraph with your own principle, idea, or belief about the app.
""",
        encoding="utf-8",
    )
    (repo / "10-architecture" / "overview.md").write_text(
        """---
id: overview
title: Overview
audience: explanation
tier: 2
status: draft
---

# Overview

Replace the diagram and prose to match your system.
""",
        encoding="utf-8",
    )

    assert _flagged_ids(repo) == {"principles", "overview"}


def test_real_foundation_content_not_flagged(fixture_repo: Callable[[str], Path]) -> None:
    repo = fixture_repo("soft-foundation-fresh")
    assert "laws" not in _flagged_ids(repo)


def test_component_layer_not_scoped(fixture_repo: Callable[[str], Path]) -> None:
    """A component doc quoting a scaffold phrase is outside the check's scope."""
    repo = fixture_repo("soft-foundation-fresh")
    assert "widget" not in _flagged_ids(repo)


def test_findings_carry_a_suggestion(fixture_repo: Callable[[str], Path]) -> None:
    repo = fixture_repo("soft-foundation-fresh")
    config = load(find_config(repo))
    graph = build_graph(repo, config)
    findings = FoundationReadinessCheck().run(graph)
    principles = next(f for f in findings if f.doc_id == "principles")
    assert principles.suggestion is not None
    assert "irminsul seed" in principles.suggestion
