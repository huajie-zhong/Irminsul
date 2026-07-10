"""Unit tests for change transitions (RFC-0029)."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

import pytest

from irminsul.change.report import ChangeError
from irminsul.change.transition import plan_transition
from irminsul.config import IrminsulConfig, find_config, load
from irminsul.docgraph import DocGraph, build_graph
from irminsul.fix import apply_fixes

_ADR = "docs/50-decisions/0001-adr.md"


@pytest.fixture
def repo(fixture_repo: Callable[[str], Path]) -> Path:
    return fixture_repo("soft-change-binding")


def _graph(repo: Path) -> tuple[DocGraph, IrminsulConfig]:
    config = load(find_config(repo))
    return build_graph(repo, config), config


def test_accept_without_adr_blocks(repo: Path) -> None:
    graph, config = _graph(repo)
    plan = plan_transition(graph, config, "0004-draft-ready", "accepted")
    assert any(b.code == "missing-adr" for b in plan.blockers)
    assert plan.fixes == ()


def test_accept_with_unresolvable_adr_blocks(repo: Path) -> None:
    graph, config = _graph(repo)
    plan = plan_transition(
        graph, config, "0004-draft-ready", "accepted", resolved_by="docs/50-decisions/none.md"
    )
    assert any(b.code == "unresolved-adr" for b in plan.blockers)


def test_accept_without_affects_blocks(repo: Path) -> None:
    path = repo / "docs" / "80-evolution" / "rfcs" / "0004-draft-ready.md"
    text = path.read_text(encoding="utf-8").replace("affects:\n  - auth\n", "")
    path.write_text(text, encoding="utf-8")

    graph, config = _graph(repo)
    plan = plan_transition(graph, config, "0004-draft-ready", "accepted", resolved_by=_ADR)
    assert any(b.code == "missing-affects" for b in plan.blockers)


def test_accept_plan_contains_coupled_edits(repo: Path) -> None:
    graph, config = _graph(repo)
    plan = plan_transition(graph, config, "0004-draft-ready", "accepted", resolved_by=_ADR)
    assert plan.blockers == ()
    descriptions = " | ".join(fix.description for fix in plan.fixes)
    assert "rfc_state: accepted" in descriptions
    assert "status: stable" in descriptions
    assert "resolved_by" in descriptions
    assert "required_updates" in descriptions
    assert "Resolution" in descriptions
    assert all(fix.requires_confirm for fix in plan.fixes)


def test_invalid_transition_blocks(repo: Path) -> None:
    graph, config = _graph(repo)
    plan = plan_transition(graph, config, "0001-accepted-good", "accepted")
    assert any(b.code == "invalid-transition" for b in plan.blockers)


def test_implemented_target_rejected(repo: Path) -> None:
    graph, config = _graph(repo)
    with pytest.raises(ChangeError) as exc:
        plan_transition(graph, config, "0001-accepted-good", "implemented")
    assert exc.value.code == 2
    assert "finalize" in str(exc.value)


def test_reject_plan_adds_rationale_stub(repo: Path) -> None:
    graph, config = _graph(repo)
    plan = plan_transition(graph, config, "0004-draft-ready", "rejected")
    assert plan.blockers == ()
    descriptions = " | ".join(fix.description for fix in plan.fixes)
    assert "rfc_state: rejected" in descriptions
    assert "Rejection Rationale" in descriptions
    assert "required_updates" not in descriptions


def test_accept_apply_end_to_end(repo: Path) -> None:
    graph, config = _graph(repo)
    plan = plan_transition(graph, config, "0004-draft-ready", "accepted", resolved_by=_ADR)
    result = apply_fixes(repo, list(plan.fixes), dry_run=False, confirm=True)
    assert result.errors == []

    updated = build_graph(repo, config).nodes["0004-draft-ready"]
    fm = updated.frontmatter
    assert fm.rfc_state is not None and fm.rfc_state.value == "accepted"
    assert fm.status.value == "stable"
    assert fm.resolved_by == _ADR
    assert fm.required_updates == []
    assert "## Resolution" in updated.body
