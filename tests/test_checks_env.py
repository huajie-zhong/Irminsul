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


def test_undeclared_env_var_flagged(fixture_repo: Callable[[str], Path]) -> None:
    repo = fixture_repo("bad-env")
    findings = _findings(repo)
    undeclared = [f for f in findings if "used in code but not declared" in f.message]
    assert any("DB_URL" in f.message for f in undeclared)


def test_stale_env_var_flagged(fixture_repo: Callable[[str], Path]) -> None:
    repo = fixture_repo("bad-env")
    findings = _findings(repo)
    stale = [f for f in findings if "stale" in f.message]
    assert any("WRONG_KEY" in f.message for f in stale)


def test_no_requires_env_field_skipped(fixture_repo: Callable[[str], Path]) -> None:
    repo = fixture_repo("good")
    assert _findings(repo) == []
