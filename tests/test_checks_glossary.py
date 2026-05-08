"""Tests for GlossaryCheck."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from irminsul.checks.glossary import GlossaryCheck, _parse_glossary_terms
from irminsul.config import find_config, load
from irminsul.docgraph import build_graph


def test_redefined_term_warned(fixture_repo: Callable[[str], Path]) -> None:
    repo = fixture_repo("soft-glossary")
    config = load(find_config(repo))
    graph = build_graph(repo, config)
    findings = GlossaryCheck().run(graph)
    flagged_ids = {f.doc_id for f in findings}
    assert "composer" in flagged_ids


def test_benign_mention_not_warned(fixture_repo: Callable[[str], Path]) -> None:
    repo = fixture_repo("soft-glossary")
    config = load(find_config(repo))
    graph = build_graph(repo, config)
    findings = GlossaryCheck().run(graph)
    flagged_ids = {f.doc_id for f in findings}
    assert "benign" not in flagged_ids


def test_missing_glossary_returns_empty(tmp_path: Path) -> None:
    """No GLOSSARY.md → silent skip (project hasn't bootstrapped one)."""
    repo = tmp_path / "r"
    repo.mkdir()
    (repo / "irminsul.toml").write_text(
        'project_name = "r"\n'
        '[paths]\ndocs_root = "docs"\nsource_roots = []\n'
        '[checks]\nsoft_deterministic = ["glossary"]\n',
        encoding="utf-8",
    )
    (repo / "docs").mkdir()

    config = load(find_config(repo))
    graph = build_graph(repo, config)
    assert GlossaryCheck().run(graph) == []


def test_parse_glossary_separates_anti_terms() -> None:
    text = (
        "# Glossary\n\n"
        "## Composer\n\nThe composer.\n\n"
        "## Planner\n\nThe planner.\n\n"
        "## Anti-Glossary\n\n"
        "- thing\n"
        "- stuff\n"
    )
    terms, anti = _parse_glossary_terms(text)
    assert terms == {"Composer", "Planner"}
    assert "thing" in anti
    assert "stuff" in anti
