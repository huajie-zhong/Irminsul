"""Tests for the foundation-readiness check."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from irminsul.checks.foundation_readiness import FoundationReadinessCheck
from irminsul.init.placeholders import placeholder_lines

from .conftest import run_check


def _flagged_ids(repo: Path) -> set[str]:
    return {f.doc_id for f in run_check(FoundationReadinessCheck, repo)}


def test_scaffold_placeholders_flagged(fixture_repo: Callable[[str], Path]) -> None:
    repo = fixture_repo("soft-foundation-fresh")
    flagged = _flagged_ids(repo)
    assert "principles" in flagged
    assert "overview" in flagged


def test_scaffold_placeholders_flagged_when_docs_root_is_repo_root(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    (repo / "foundation").mkdir(parents=True)
    (repo / "architecture").mkdir()
    (repo / "irminsul.toml").write_text(
        'project_name = "root-docs"\n[paths]\ndocs_root = "."\nsource_roots = []\n',
        encoding="utf-8",
    )
    (repo / "foundation" / "principles.md").write_text(
        """---
id: principles
title: Principles
status: draft
---

# Principles

Replace this paragraph with your own principle. <!-- irminsul:placeholder -->
""",
        encoding="utf-8",
    )
    (repo / "architecture" / "overview.md").write_text(
        """---
id: overview
title: Overview
status: draft
---

# Overview

Replace the diagram and prose to match your system. <!-- irminsul:placeholder -->
""",
        encoding="utf-8",
    )

    assert _flagged_ids(repo) == {"principles", "overview"}


def test_real_foundation_content_not_flagged(fixture_repo: Callable[[str], Path]) -> None:
    """`laws` quotes the marker in a code span and a fence, which mark nothing."""
    repo = fixture_repo("soft-foundation-fresh")
    assert "laws" not in _flagged_ids(repo)


def test_a_finding_points_at_the_first_marked_prompt(fixture_repo: Callable[[str], Path]) -> None:
    repo = fixture_repo("soft-foundation-fresh")
    principles = next(
        f for f in run_check(FoundationReadinessCheck, repo) if f.doc_id == "principles"
    )
    lines = (repo / "docs/foundation/principles.md").read_text(encoding="utf-8").splitlines()
    assert principles.line is not None
    assert lines[principles.line - 1].startswith("> _Replace this paragraph")


def test_a_marker_alone_on_its_line_covers_the_block_after_it() -> None:
    body = "\n".join(
        [
            "Intro.",
            "",
            "<!-- irminsul:placeholder -->",
            "```mermaid",
            "graph TD",
            "",
            "  a --> b",
            "```",
            "",
            "Authored. `<!-- irminsul:placeholder -->` is an example.",
            "- _A prompt._ <!-- irminsul:placeholder -->",
        ]
    )
    assert placeholder_lines(body) == [3, 4, 5, 6, 7, 8, 11]


def test_component_layer_not_scoped(fixture_repo: Callable[[str], Path]) -> None:
    """A component doc quoting a scaffold phrase is outside the check's scope."""
    repo = fixture_repo("soft-foundation-fresh")
    assert "widget" not in _flagged_ids(repo)


def test_findings_carry_a_suggestion(fixture_repo: Callable[[str], Path]) -> None:
    repo = fixture_repo("soft-foundation-fresh")
    findings = run_check(FoundationReadinessCheck, repo)
    principles = next(f for f in findings if f.doc_id == "principles")
    assert principles.suggestion is not None
    assert "irminsul seed" in principles.suggestion
