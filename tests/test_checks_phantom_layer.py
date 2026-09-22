"""Tests for PhantomLayerCheck."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from irminsul.checks.base import Severity
from irminsul.checks.phantom_layer import PhantomLayerCheck
from irminsul.config import find_config, load
from irminsul.docgraph import build_graph


def _findings(repo: Path) -> list:
    config = load(find_config(repo))
    graph = build_graph(repo, config)
    return PhantomLayerCheck().run(graph)


def test_good_fixture_has_no_phantom_findings(fixture_repo: Callable[[str], Path]) -> None:
    repo = fixture_repo("good")
    findings = _findings(repo)
    assert findings == []


def test_hollow_stable_directory_is_an_error(fixture_repo: Callable[[str], Path]) -> None:
    """A hollow layer whose INDEX is `stable` is an error."""
    repo = fixture_repo("bad-phantom")
    errors = [f for f in _findings(repo) if f.severity == Severity.error]
    assert len(errors) == 1
    assert "phantom layer" in errors[0].message
    assert "guides" in errors[0].message


def test_finding_has_path(fixture_repo: Callable[[str], Path]) -> None:
    repo = fixture_repo("bad-phantom")
    findings = _findings(repo)
    assert findings
    for f in findings:
        assert f.path is not None
        assert str(f.path).endswith("INDEX.md")


def test_draft_index_downgrades_to_info(fixture_repo: Callable[[str], Path]) -> None:
    """A hollow `status: draft` layer is reported as info, not a warning.

    The fixture has two hollow layers: `guides` (stable INDEX, warning)
    and `operations` (draft INDEX, info — under construction, non-gating).
    """
    findings = _findings(fixture_repo("bad-phantom"))
    infos = [f for f in findings if f.severity == Severity.info]
    assert len(infos) == 1
    assert "operations" in infos[0].message
    assert "under construction" in infos[0].message
    # The draft layer never produces a gating warning.
    assert all("operations" not in f.message for f in findings if f.severity == Severity.warning)
