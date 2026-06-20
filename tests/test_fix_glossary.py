"""Tests for GlossaryDisciplineCheck.fixes (RFC 0022 item 5)."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from irminsul.checks.glossary import GlossaryDisciplineCheck
from irminsul.config import find_config, load
from irminsul.docgraph import build_graph
from irminsul.fix import apply_fixes


def _fixes(repo: Path) -> list:
    config = load(find_config(repo))
    graph = build_graph(repo, config)
    check = GlossaryDisciplineCheck()
    return check.fixes(check.run(graph), graph)


def test_autolink_requires_confirm_and_wraps_first_use(
    fixture_repo: Callable[[str], Path],
) -> None:
    repo = fixture_repo("soft-glossary")
    fixes = _fixes(repo)
    benign = repo / "docs" / "20-components" / "benign.md"

    benign_fixes = [f for f in fixes if f.path == Path("docs/20-components/benign.md")]
    assert len(benign_fixes) == 1
    assert benign_fixes[0].requires_confirm is True

    before = benign.read_text(encoding="utf-8")
    apply_fixes(repo, fixes, dry_run=False, confirm=False)
    assert benign.read_text(encoding="utf-8") == before  # held

    apply_fixes(repo, fixes, dry_run=False, confirm=True)
    text = benign.read_text(encoding="utf-8")
    assert "[Composer](../GLOSSARY.md#composer)" in text


def test_autolink_is_idempotent(fixture_repo: Callable[[str], Path]) -> None:
    repo = fixture_repo("soft-glossary")
    apply_fixes(repo, _fixes(repo), dry_run=False, confirm=True)
    benign = repo / "docs" / "20-components" / "benign.md"
    once = benign.read_text(encoding="utf-8")

    # Second pass must not double-wrap the now-linked term.
    apply_fixes(repo, _fixes(repo), dry_run=False, confirm=True)
    assert benign.read_text(encoding="utf-8") == once
    assert once.count("](../GLOSSARY.md#composer)") == 1
