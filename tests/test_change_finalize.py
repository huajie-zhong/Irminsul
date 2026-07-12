"""Unit tests for change finalization (RFC-0032)."""

from __future__ import annotations

import subprocess
from collections.abc import Callable
from pathlib import Path

import pytest

from irminsul.change.finalize import parse_binding_flags, plan_finalize
from irminsul.change.report import ChangeError
from irminsul.config import IrminsulConfig, find_config, load
from irminsul.docgraph import DocGraph, build_graph
from irminsul.fix import apply_fixes

_ADR = "docs/50-decisions/0001-adr.md"
_RFC = "0001-accepted-good"
_BINDINGS = {
    "sso-login": ["app/auth/login.py#login", "tests/test_auth.py#test_login"],
}


@pytest.fixture
def repo(fixture_repo: Callable[[str], Path]) -> Path:
    return _committed(fixture_repo("soft-change-binding"))


@pytest.fixture
def edges(fixture_repo: Callable[[str], Path]) -> Path:
    return _committed(fixture_repo("change-finalize-edges"))


def _committed(root: Path) -> Path:
    _git(root, "init", "-q")
    _git(root, "config", "user.email", "test@example.com")
    _git(root, "config", "user.name", "Test")
    _git(root, "add", ".")
    _git(root, "commit", "-q", "-m", "init")
    return root


def _git(repo: Path, *args: str) -> None:
    subprocess.run(["git", "-C", str(repo), *args], check=True, capture_output=True, text=True)


def _graph(repo: Path) -> tuple[DocGraph, IrminsulConfig]:
    config = load(find_config(repo))
    return build_graph(repo, config), config


def test_parse_binding_flags() -> None:
    parsed = parse_binding_flags(["a=src/x.py#f", "a=tests/t.py#g", "b=src/y.py"], "--anchor")
    assert parsed == {"a": ["src/x.py#f", "tests/t.py#g"], "b": ["src/y.py"]}


def test_parse_binding_flags_malformed() -> None:
    with pytest.raises(ChangeError):
        parse_binding_flags(["no-equals"], "--anchor")


def test_finalize_plan_promotes_and_transitions(repo: Path) -> None:
    graph, config = _graph(repo)
    plan = plan_finalize(graph, config, repo, _RFC, bindings=_BINDINGS, env={})
    assert plan.blockers == ()
    [promotion] = plan.promotions
    assert promotion.global_id == "0001-accepted-good#sso-login"
    assert promotion.owner == "auth"
    assert len(promotion.anchors) == 2
    assert all("@sha256:" in payload for payload in promotion.anchors)
    descriptions = " | ".join(f.description for f in plan.component_fixes)
    assert "promote 0001-accepted-good#sso-login" in descriptions
    assert "implements: 0001-accepted-good" in descriptions
    rfc_descriptions = " | ".join(f.description for f in plan.rfc_fixes)
    assert "rfc_state: implemented" in rfc_descriptions


def test_finalize_missing_binding_blocks(repo: Path) -> None:
    graph, config = _graph(repo)
    plan = plan_finalize(graph, config, repo, _RFC, env={})
    assert any(b.code == "missing-binding" for b in plan.blockers)


def test_finalize_unresolvable_binding_blocks(repo: Path) -> None:
    graph, config = _graph(repo)
    plan = plan_finalize(
        graph,
        config,
        repo,
        _RFC,
        bindings={"sso-login": ["app/auth/login.py#does_not_exist"]},
        env={},
    )
    assert any(b.code == "unresolvable-binding" for b in plan.blockers)


def test_finalize_unknown_requirement_binding_blocks(repo: Path) -> None:
    graph, config = _graph(repo)
    plan = plan_finalize(
        graph,
        config,
        repo,
        _RFC,
        bindings={**_BINDINGS, "ghost": ["app/auth/login.py#login"]},
        env={},
    )
    assert any(b.code == "unknown-requirement" for b in plan.blockers)


def test_finalize_conflicting_owner_choices_block(repo: Path) -> None:
    graph, config = _graph(repo)
    plan = plan_finalize(
        graph,
        config,
        repo,
        _RFC,
        bindings=_BINDINGS,
        owners={"sso-login": ["auth", "billing"]},
        env={},
    )
    assert any(b.code == "conflicting-owner" for b in plan.blockers)


def test_finalize_rfc_link_is_relative(repo: Path) -> None:
    graph, config = _graph(repo)
    plan = plan_finalize(graph, config, repo, _RFC, bindings=_BINDINGS, env={})
    assert plan.blockers == ()
    component_result = apply_fixes(repo, list(plan.component_fixes), dry_run=False, confirm=True)
    assert component_result.errors == []
    owner_text = (repo / "docs" / "20-components" / "auth.md").read_text(encoding="utf-8")
    assert "[RFC](../80-evolution/rfcs/0001-accepted-good.md)" in owner_text


def test_finalize_draft_rfc_blocks(repo: Path) -> None:
    graph, config = _graph(repo)
    plan = plan_finalize(graph, config, repo, "0004-draft-ready", env={})
    assert any(b.code == "invalid-state" for b in plan.blockers)


def test_finalize_unknown_baseline_blocks(fixture_repo: Callable[[str], Path]) -> None:
    repo = fixture_repo("soft-change-binding")  # deliberately not a git repo
    graph, config = _graph(repo)
    plan = plan_finalize(graph, config, repo, _RFC, bindings=_BINDINGS, env={})
    assert any(b.code == "unknown-baseline" for b in plan.blockers)


def test_finalize_unreconciled_scope_blocks(repo: Path) -> None:
    (repo / "app" / "billing" / "extra.py").write_text("x = 1\n", encoding="utf-8")
    graph, config = _graph(repo)
    plan = plan_finalize(graph, config, repo, _RFC, bindings=_BINDINGS, env={})
    assert any(b.code == "unreconciled-scope" for b in plan.blockers)


def test_finalize_apply_end_to_end_and_idempotent(repo: Path) -> None:
    graph, config = _graph(repo)
    plan = plan_finalize(graph, config, repo, _RFC, bindings=_BINDINGS, env={})
    assert plan.blockers == ()

    component_result = apply_fixes(repo, list(plan.component_fixes), dry_run=False, confirm=True)
    assert component_result.errors == []
    rfc_result = apply_fixes(repo, list(plan.rfc_fixes), dry_run=False, confirm=True)
    assert rfc_result.errors == []

    graph2, _ = _graph(repo)
    owner = graph2.nodes["auth"]
    assert "## Implemented requirements" in owner.body
    assert "**0001-accepted-good#sso-login**" in owner.body
    assert "<!-- anchor: app/auth/login.py#login @sha256:" in owner.body
    assert "<!-- anchor: tests/test_auth.py#test_login @sha256:" in owner.body
    assert "0001-accepted-good" in owner.frontmatter.implements

    rfc = graph2.nodes[_RFC]
    assert rfc.frontmatter.rfc_state is not None
    assert rfc.frontmatter.rfc_state.value == "implemented"

    # Second run against the identical implemented RFC plans no writes.
    plan2 = plan_finalize(graph2, config, repo, _RFC, bindings=_BINDINGS, env={})
    assert plan2.blockers == ()
    assert plan2.component_fixes == ()
    assert plan2.rfc_fixes == ()
    assert any("already" in note for note in plan2.notes)


def test_finalize_binding_path_is_posix_normalized(repo: Path) -> None:
    graph, config = _graph(repo)
    plan = plan_finalize(
        graph,
        config,
        repo,
        _RFC,
        bindings={"sso-login": ["app\\auth\\login.py#login"]},
        env={},
    )
    assert plan.blockers == ()
    [promotion] = plan.promotions
    assert promotion.anchors[0].startswith("app/auth/login.py#login @sha256:")

    result = apply_fixes(repo, list(plan.component_fixes), dry_run=False, confirm=True)
    assert result.errors == []
    owner_text = (repo / "docs" / "20-components" / "auth.md").read_text(encoding="utf-8")
    assert "<!-- anchor: app/auth/login.py#login @sha256:" in owner_text
    assert "\\" not in owner_text


def test_finalize_unknown_owner_requirement_blocks(repo: Path) -> None:
    graph, config = _graph(repo)
    plan = plan_finalize(
        graph,
        config,
        repo,
        _RFC,
        bindings=_BINDINGS,
        owners={"sso-logn": ["billing"]},
        env={},
    )
    unknown = [b for b in plan.blockers if b.code == "unknown-requirement"]
    assert unknown and "--owner" in unknown[0].message
    assert plan.component_fixes == ()


def test_finalize_already_promoted_still_adds_backlink(repo: Path) -> None:
    owner_path = repo / "docs" / "20-components" / "auth.md"
    owner_path.write_text(
        owner_path.read_text(encoding="utf-8")
        + "\n## Implemented requirements\n\n"
        + "- **0001-accepted-good#sso-login** — hand-authored entry (provenance: code)\n",
        encoding="utf-8",
    )
    graph, config = _graph(repo)
    plan = plan_finalize(graph, config, repo, _RFC, bindings=_BINDINGS, env={})
    assert plan.blockers == ()
    [promotion] = plan.promotions
    assert promotion.already_promoted
    descriptions = [f.description for f in plan.component_fixes]
    assert descriptions == ["add implements: 0001-accepted-good to docs/20-components/auth.md"]

    result = apply_fixes(repo, list(plan.component_fixes), dry_run=False, confirm=True)
    assert result.errors == []
    graph2, _ = _graph(repo)
    assert "0001-accepted-good" in graph2.nodes["auth"].frontmatter.implements


def test_finalize_required_update_backlink_is_not_a_deadlock(edges: Path) -> None:
    graph, config = _graph(edges)
    plan = plan_finalize(
        graph,
        config,
        edges,
        "0002-required-update",
        bindings={"login-flow": ["app/auth/login.py#login"]},
        env={},
    )
    assert plan.blockers == ()
    descriptions = " | ".join(f.description for f in plan.component_fixes)
    assert "add implements: 0002-required-update to docs/20-components/auth.md" in descriptions

    component_result = apply_fixes(edges, list(plan.component_fixes), dry_run=False, confirm=True)
    assert component_result.errors == []
    graph2, _ = _graph(edges)
    assert "0002-required-update" in graph2.nodes["auth"].frontmatter.implements


def test_finalize_binding_on_non_code_requirement_blocks(edges: Path) -> None:
    graph, config = _graph(edges)
    plan = plan_finalize(
        graph,
        config,
        edges,
        "0003-adr-provenance",
        bindings={"retention-window": ["app/auth/login.py#login"]},
        env={},
    )
    assert any(b.code == "unsupported-binding" for b in plan.blockers)


def test_finalize_non_code_requirement_promotes_without_anchors(edges: Path) -> None:
    graph, config = _graph(edges)
    plan = plan_finalize(graph, config, edges, "0003-adr-provenance", env={})
    assert plan.blockers == ()
    [promotion] = plan.promotions
    assert promotion.owner == "auth"
    assert promotion.provenance == "adr"
    assert promotion.anchors == ()


def test_finalize_nested_owner_uses_most_specific_claim(edges: Path) -> None:
    graph, config = _graph(edges)
    plan = plan_finalize(
        graph,
        config,
        edges,
        "0001-nested-owner",
        bindings={"route-table": ["app/auth/routing/router.py#route"]},
        env={},
    )
    assert plan.blockers == ()
    [promotion] = plan.promotions
    assert promotion.owner == "auth-routing"


def test_finalize_disposition_rfc_needs_no_bindings(repo: Path) -> None:
    path = repo / "docs" / "80-evolution" / "rfcs" / "0007-draft-disposition.md"
    text = path.read_text(encoding="utf-8")
    text = text.replace("rfc_state: draft", "rfc_state: accepted")
    text = text.replace("status: draft", "status: stable")
    text = text.replace(
        "---\n\n# RFC 0007",
        "resolved_by: docs/50-decisions/0001-adr.md\nrequired_updates: []\n---\n\n# RFC 0007",
    )
    text += "\n## Resolution\n\nApproved; see [ADR-0001](../../50-decisions/0001-adr.md).\n"
    path.write_text(text, encoding="utf-8")

    graph, config = _graph(repo)
    plan = plan_finalize(graph, config, repo, "0007-draft-disposition", env={})
    assert plan.blockers == ()
    assert plan.promotions == ()
    rfc_descriptions = " | ".join(f.description for f in plan.rfc_fixes)
    assert "rfc_state: implemented" in rfc_descriptions
