"""Tests for `StaleReaperCheck`."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from irminsul.checks.stale_reaper import StaleReaperCheck
from irminsul.config import find_config, load
from irminsul.docgraph import build_graph


def test_old_deprecated_doc_flagged(fixture_repo: Callable[[str], Path]) -> None:
    repo = fixture_repo("soft-stale-reaper")
    config = load(find_config(repo))
    graph = build_graph(repo, config)

    findings = StaleReaperCheck().run(graph)
    flagged_ids = {f.doc_id for f in findings}
    assert "stale" in flagged_ids


def test_recent_deprecation_not_flagged(fixture_repo: Callable[[str], Path]) -> None:
    repo = fixture_repo("soft-stale-reaper")
    config = load(find_config(repo))
    graph = build_graph(repo, config)

    findings = StaleReaperCheck().run(graph)
    flagged_ids = {f.doc_id for f in findings}
    assert "recent-deprecation" not in flagged_ids


def test_stable_doc_not_flagged(fixture_repo: Callable[[str], Path]) -> None:
    repo = fixture_repo("soft-stale-reaper")
    config = load(find_config(repo))
    graph = build_graph(repo, config)

    findings = StaleReaperCheck().run(graph)
    flagged_ids = {f.doc_id for f in findings}
    assert "fresh" not in flagged_ids


def test_finding_carries_suggestion(fixture_repo: Callable[[str], Path]) -> None:
    repo = fixture_repo("soft-stale-reaper")
    config = load(find_config(repo))
    graph = build_graph(repo, config)

    findings = StaleReaperCheck().run(graph)
    stale = next(f for f in findings if f.doc_id == "stale")
    assert stale.suggestion is not None
    assert "remove" in stale.suggestion or "rewrite" in stale.suggestion
