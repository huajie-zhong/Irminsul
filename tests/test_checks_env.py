"""Tests for EnvCheck (requires-env)."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from irminsul.checks.env_check import EnvCheck
from irminsul.config import find_config, load
from irminsul.docgraph import build_graph


def _findings(repo: Path) -> list:
    config = load(find_config(repo))
    graph = build_graph(repo, config)
    return EnvCheck().run(graph)


def test_good_fixture_no_findings(fixture_repo: Callable[[str], Path]) -> None:
    repo = fixture_repo("good-env")
    assert _findings(repo) == []


def test_undeclared_env_var_not_flagged(fixture_repo: Callable[[str], Path]) -> None:
    # RFC 0020 intent-only: an env var used in code but not declared is NOT flagged
    # (that completeness direction was the materialization pressure we removed).
    repo = fixture_repo("bad-env")
    findings = _findings(repo)
    assert not [f for f in findings if "used in code but not declared" in f.message]


def test_stale_env_var_flagged(fixture_repo: Callable[[str], Path]) -> None:
    repo = fixture_repo("bad-env")
    findings = _findings(repo)
    stale = [f for f in findings if "stale" in f.message]
    assert any("WRONG_KEY" in f.message for f in stale)


def test_no_requires_env_field_skipped(fixture_repo: Callable[[str], Path]) -> None:
    repo = fixture_repo("good")
    assert _findings(repo) == []
