"""Tests for the GlobsCheck."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from irminsul.checks import Severity
from irminsul.checks.globs import GlobsCheck
from irminsul.config import load
from irminsul.docgraph import build_graph


def _run(repo: Path) -> list:
    cfg = load(repo / "irminsul.toml")
    graph = build_graph(repo, cfg)
    return GlobsCheck().run(graph)


def test_good_fixture_has_no_glob_findings(
    fixture_repo: Callable[[str], Path],
) -> None:
    findings = _run(fixture_repo("good"))
    assert [f for f in findings if f.severity == Severity.error] == []


def test_bad_globs_fixture_flags_each_unmatched_pattern(
    fixture_repo: Callable[[str], Path],
) -> None:
    findings = _run(fixture_repo("bad-globs"))
    error_messages = [f.message for f in findings if f.severity == Severity.error]

    # The real pattern (app/real.py) should NOT be flagged.
    assert not any("app/real.py" in m for m in error_messages)
    # The two dead patterns should both be flagged.
    assert any("app/missing/*.py" in m for m in error_messages)
    assert any("lib/ghost.py" in m for m in error_messages)


def test_missing_source_root_emits_warning(tmp_path: Path) -> None:
    (tmp_path / "irminsul.toml").write_text(
        'project_name = "missing-root"\n\n'
        '[paths]\ndocs_root = "docs"\nsource_roots = ["does-not-exist"]\n',
        encoding="utf-8",
    )
    (tmp_path / "docs" / "20-components").mkdir(parents=True)
    (tmp_path / "docs" / "20-components" / "x.md").write_text(
        "---\n"
        "id: x\n"
        "title: X\n"
        "audience: explanation\n"
        "tier: 3\n"
        "status: stable\n"
        "---\nbody\n",
        encoding="utf-8",
    )
    cfg = load(tmp_path / "irminsul.toml")
    graph = build_graph(tmp_path, cfg)
    findings = GlobsCheck().run(graph)

    assert any(f.severity == Severity.warning and "does-not-exist" in f.message for f in findings)
