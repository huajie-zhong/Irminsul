"""Tests for explicit pre-lifecycle RFC migration."""

from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path

import pytest

from irminsul.change.migrate import (
    get_candidate,
    inventory_candidates,
    inventory_to_json,
    plan_migration,
)
from irminsul.change.report import ChangeError
from irminsul.config import load
from irminsul.docgraph import build_graph
from irminsul.fix import apply_fixes
from irminsul.frontmatter import (
    LifecycleMigrationBasisEnum,
    RfcStateEnum,
    parse_doc,
)
from irminsul.rfc_freeze import compute_frozen_hash


def _repo(tmp_path: Path) -> Path:
    (tmp_path / "docs" / "20-components").mkdir(parents=True)
    (tmp_path / "docs" / "50-decisions").mkdir(parents=True)
    (tmp_path / "docs" / "80-evolution" / "rfcs").mkdir(parents=True)
    (tmp_path / "irminsul.toml").write_text(
        'project_name = "migration"\n[paths]\ndocs_root = "docs"\nsource_roots = []\n',
        encoding="utf-8",
    )
    (tmp_path / "docs" / "20-components" / "widget.md").write_text(
        "---\n"
        "id: widget\n"
        "title: Widget\n"
        "audience: explanation\n"
        "tier: 3\n"
        "status: stable\n"
        "describes: []\n"
        "---\n\n"
        "# Widget\n",
        encoding="utf-8",
    )
    return tmp_path


def _write_rfc(
    repo: Path,
    *,
    doc_id: str = "0001-legacy",
    state: str | None = None,
    requirements: bool = False,
) -> Path:
    state_line = f"rfc_state: {state}\n" if state else ""
    body = "# Legacy RFC\n\nProposal.\n"
    if requirements:
        body += (
            "\n## Requirements\n\n"
            "No new behavioral requirements: migration classifies existing history.\n"
        )
    path = repo / "docs" / "80-evolution" / "rfcs" / f"{doc_id}.md"
    path.write_text(
        "---\n"
        f"id: {doc_id}\n"
        "title: Legacy RFC\n"
        "audience: explanation\n"
        "tier: 2\n"
        "status: stable\n"
        "describes: []\n"
        f"{state_line}"
        "---\n\n"
        f"{body}",
        encoding="utf-8",
    )
    return path


def _write_adr(repo: Path, rfc_id: str = "0001-legacy") -> str:
    rel = "docs/50-decisions/0001-legacy-decision.md"
    (repo / rel).write_text(
        "---\n"
        "id: 0001-legacy-decision\n"
        "title: Legacy decision\n"
        "audience: adr\n"
        "tier: 2\n"
        "status: stable\n"
        "describes: []\n"
        "---\n\n"
        "# Legacy decision\n\n"
        f"Resolves [the RFC](../80-evolution/rfcs/{rfc_id}.md).\n",
        encoding="utf-8",
    )
    return rel


def _graph(repo: Path):
    config = load(repo / "irminsul.toml")
    return build_graph(repo, config), config


def test_inventory_is_sorted_excludes_index_and_never_recommends_state(
    tmp_path: Path,
) -> None:
    repo = _repo(tmp_path)
    _write_rfc(repo, doc_id="0002-second")
    _write_rfc(repo, doc_id="0001-first")
    _write_rfc(repo, doc_id="0003-modern", state="draft")
    (repo / "docs" / "80-evolution" / "rfcs" / "INDEX.md").write_text(
        "---\n"
        "id: rfcs\n"
        "title: RFCs\n"
        "audience: explanation\n"
        "tier: 2\n"
        "status: stable\n"
        "---\n\n# RFCs\n",
        encoding="utf-8",
    )
    graph, config = _graph(repo)

    candidates = inventory_candidates(graph, config)
    payload = json.loads(inventory_to_json(candidates))

    assert [candidate.id for candidate in candidates] == ["0001-first", "0002-second"]
    assert payload["state_inference"] is False
    assert all(candidate["recommended_state"] is None for candidate in payload["candidates"])


def test_candidate_evidence_reports_decisions_implementations_and_headings(
    tmp_path: Path,
) -> None:
    repo = _repo(tmp_path)
    _write_rfc(repo)
    decision = _write_adr(repo)
    component = repo / "docs" / "20-components" / "widget.md"
    component.write_text(
        component.read_text(encoding="utf-8").replace(
            "describes: []\n", "describes: []\nimplements: [0001-legacy]\n"
        ),
        encoding="utf-8",
    )
    graph, config = _graph(repo)

    _, candidate = get_candidate(graph, config, "1")

    assert candidate.decision_links == (decision,)
    assert candidate.implementation_backlinks == ("docs/20-components/widget.md",)
    assert candidate.headings == ("Legacy RFC",)


def test_modern_rfc_is_not_a_candidate(tmp_path: Path) -> None:
    repo = _repo(tmp_path)
    _write_rfc(repo, state="draft")
    graph, config = _graph(repo)

    with pytest.raises(ChangeError, match="not a pre-lifecycle"):
        get_candidate(graph, config, "0001-legacy")


def test_draft_plan_is_read_only_until_applied(tmp_path: Path) -> None:
    repo = _repo(tmp_path)
    path = _write_rfc(repo)
    before = path.read_text(encoding="utf-8")
    graph, config = _graph(repo)

    plan = plan_migration(graph, config, "0001-legacy", "draft")

    assert plan.blockers == ()
    assert plan.fix is not None
    assert path.read_text(encoding="utf-8") == before
    dry = apply_fixes(repo, [plan.fix], dry_run=True, confirm=True)
    assert dry.written == []
    assert path.read_text(encoding="utf-8") == before

    applied = apply_fixes(repo, [plan.fix], dry_run=False, confirm=True)
    assert applied.written == [Path("docs/80-evolution/rfcs/0001-legacy.md")]
    parsed = parse_doc(path, repo)
    assert not hasattr(parsed, "error")
    assert parsed.frontmatter.rfc_state == RfcStateEnum.draft
    assert parsed.frontmatter.lifecycle_migration is not None
    assert (
        parsed.frontmatter.lifecycle_migration.basis
        == LifecycleMigrationBasisEnum.human_classification
    )


def test_accepted_requires_decision_scope_updates_and_requirements(tmp_path: Path) -> None:
    repo = _repo(tmp_path)
    _write_rfc(repo)
    graph, config = _graph(repo)

    plan = plan_migration(graph, config, "0001-legacy", "accepted")

    codes = {blocker.code for blocker in plan.blockers}
    assert "missing-affects-decision" in codes
    assert "missing-required-updates-decision" in codes
    assert "missing-decision" in codes
    assert "missing-requirements" in codes


def test_accepted_migration_uses_explicit_authorized_inputs(tmp_path: Path) -> None:
    repo = _repo(tmp_path)
    path = _write_rfc(repo, requirements=True)
    decision = _write_adr(repo)
    graph, config = _graph(repo)

    plan = plan_migration(
        graph,
        config,
        "0001-legacy",
        "accepted",
        resolved_by=decision,
        affects=["widget"],
        no_required_updates=True,
    )

    assert plan.blockers == ()
    assert plan.fix is not None
    apply_fixes(repo, [plan.fix], dry_run=False, confirm=True)
    parsed = parse_doc(path, repo)
    assert not hasattr(parsed, "error")
    assert parsed.frontmatter.rfc_state == RfcStateEnum.accepted
    assert parsed.frontmatter.affects == ["widget"]
    assert parsed.frontmatter.required_updates == []
    assert parsed.frontmatter.resolved_by == decision
    assert "## Resolution" in path.read_text(encoding="utf-8")


def test_rejected_migration_requires_and_records_reason(tmp_path: Path) -> None:
    repo = _repo(tmp_path)
    path = _write_rfc(repo)
    graph, config = _graph(repo)

    with pytest.raises(ChangeError, match="requires --reason"):
        plan_migration(graph, config, "0001-legacy", "rejected")

    plan = plan_migration(
        graph,
        config,
        "0001-legacy",
        "rejected",
        reason="The replacement already ships.",
    )
    assert plan.fix is not None
    apply_fixes(repo, [plan.fix], dry_run=False, confirm=True)
    text = path.read_text(encoding="utf-8")
    assert "rfc_state: rejected" in text
    assert "## Rejection Rationale\n\nThe replacement already ships." in text


def test_implemented_migration_requires_attestation_and_seals_last(tmp_path: Path) -> None:
    repo = _repo(tmp_path)
    path = _write_rfc(repo)
    decision = _write_adr(repo)
    graph, config = _graph(repo)
    inputs = {
        "resolved_by": decision,
        "affects": ["widget"],
        "no_required_updates": True,
    }

    blocked = plan_migration(graph, config, "0001-legacy", "implemented", **inputs)
    assert "missing-implementation-attestation" in {blocker.code for blocker in blocked.blockers}

    plan = plan_migration(
        graph,
        config,
        "0001-legacy",
        "implemented",
        attest_implemented=True,
        **inputs,
    )
    assert plan.blockers == ()
    assert plan.fix is not None
    apply_fixes(repo, [plan.fix], dry_run=False, confirm=True)
    parsed = parse_doc(path, repo)
    assert not hasattr(parsed, "error")
    assert parsed.frontmatter.rfc_state == RfcStateEnum.implemented
    assert parsed.frontmatter.lifecycle_migration is not None
    assert (
        parsed.frontmatter.lifecycle_migration.basis
        == LifecycleMigrationBasisEnum.human_implementation_attestation
    )
    text = path.read_text(encoding="utf-8")
    assert parsed.frontmatter.frozen_hash == compute_frozen_hash(text)


def test_migration_option_conflicts_are_usage_errors(tmp_path: Path) -> None:
    repo = _repo(tmp_path)
    _write_rfc(repo)
    graph, config = _graph(repo)

    with pytest.raises(ChangeError, match="mutually exclusive"):
        plan_migration(
            graph,
            config,
            "0001-legacy",
            "accepted",
            affects=["widget"],
            affects_none=True,
        )


def test_composite_transformation_failure_leaves_rfc_unchanged(tmp_path: Path) -> None:
    repo = _repo(tmp_path)
    path = _write_rfc(repo)
    before = path.read_text(encoding="utf-8")
    graph, config = _graph(repo)
    plan = plan_migration(graph, config, "0001-legacy", "draft")
    assert plan.fix is not None

    def fail(_text: str) -> str:
        raise RuntimeError("injected migration failure")

    result = apply_fixes(
        repo,
        [replace(plan.fix, apply=fail)],
        dry_run=False,
        confirm=True,
    )

    assert result.written == []
    assert "injected migration failure" in result.errors[0]
    assert path.read_text(encoding="utf-8") == before
