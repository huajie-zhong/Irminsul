"""Tests for DecisionUpdatesCheck.fixes (RFC 0022 item 2)."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from irminsul.checks.decision_updates import DecisionUpdatesCheck
from irminsul.config import find_config, load
from irminsul.docgraph import build_graph
from irminsul.fix import apply_fixes


def _fixes(repo: Path) -> list:
    config = load(find_config(repo))
    graph = build_graph(repo, config)
    check = DecisionUpdatesCheck()
    return check.fixes(check.run(graph), graph)


def test_missing_backlink_fix_adds_implements_without_confirm(
    fixture_repo: Callable[[str], Path],
) -> None:
    repo = fixture_repo("soft-lifecycle")
    fixes = _fixes(repo)
    adr = repo / "docs" / "50-decisions" / "0004-no-backlink-adr.md"

    backlink_fixes = [
        f for f in fixes if f.path == Path("docs/50-decisions/0004-no-backlink-adr.md")
    ]
    assert len(backlink_fixes) == 1
    assert backlink_fixes[0].requires_confirm is False

    # Additive inverse pointer: applies without --confirm.
    apply_fixes(repo, fixes, dry_run=False, confirm=False)
    text = adr.read_text(encoding="utf-8")
    assert "implements:" in text
    assert "0004-no-backlink" in text


def test_backlink_fix_is_idempotent(fixture_repo: Callable[[str], Path]) -> None:
    repo = fixture_repo("soft-lifecycle")
    apply_fixes(repo, _fixes(repo), dry_run=False, confirm=False)
    # Second pass: the finding is gone, so no fix remains.
    assert _fixes(repo) == []
