"""Unit tests for change finalization."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

import pytest

from irminsul.change.finalize import FinalizePlan, parse_binding_flags, plan_finalize
from irminsul.change.report import ChangeError, build_change_report
from irminsul.checks.base import Finding
from irminsul.checks.retired_references import RetiredReferencesCheck
from irminsul.config import IrminsulConfig
from irminsul.docgraph import DocGraph
from irminsul.fix import apply_fixes

from .conftest import load_graph, seed_repo

_ADR = "docs/decisions/0001-adr.md"
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
    seed_repo(root, "init")
    return root


def _graph(repo: Path) -> tuple[DocGraph, IrminsulConfig]:
    graph = load_graph(repo)
    return graph, graph.config


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
    owner_text = (repo / "docs" / "components" / "auth.md").read_text(encoding="utf-8")
    assert "[RFC](../rfcs/0001-accepted-good.md)" in owner_text


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
    assert "frozen_hash" not in rfc.frontmatter.model_extra

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
    owner_text = (repo / "docs" / "components" / "auth.md").read_text(encoding="utf-8")
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
    owner_path = repo / "docs" / "components" / "auth.md"
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
    assert descriptions == ["add implements: 0001-accepted-good to docs/components/auth.md"]

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
    assert "add implements: 0002-required-update to docs/components/auth.md" in descriptions

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
    path = repo / "docs" / "rfcs" / "0007-draft-disposition.md"
    text = path.read_text(encoding="utf-8")
    text = text.replace("rfc_state: draft", "rfc_state: accepted")
    text = text.replace("status: draft", "status: stable")
    text = text.replace(
        "---\n\n# RFC 0007",
        "resolved_by: docs/decisions/0001-adr.md\nrequired_updates: []\n---\n\n# RFC 0007",
    )
    text += "\n## Resolution\n\nApproved; see [ADR-0001](../decisions/0001-adr.md).\n"
    path.write_text(text, encoding="utf-8")

    graph, config = _graph(repo)
    plan = plan_finalize(graph, config, repo, "0007-draft-disposition", env={})
    assert plan.blockers == ()
    assert plan.promotions == ()
    rfc_descriptions = " | ".join(f.description for f in plan.rfc_fixes)
    assert "rfc_state: implemented" in rfc_descriptions


def test_finalize_backlinks_every_required_update_doc(repo: Path) -> None:
    path = repo / "docs" / "rfcs" / "0007-draft-disposition.md"
    text = path.read_text(encoding="utf-8")
    text = text.replace("rfc_state: draft", "rfc_state: accepted")
    text = text.replace("status: draft", "status: stable")
    text = text.replace(
        "---\n\n# RFC 0007",
        "resolved_by: docs/decisions/0001-adr.md\nrequired_updates:\n"
        "  - path: docs/components/auth.md\n    kind: update\n---\n\n# RFC 0007",
    )
    text += "\n## Resolution\n\nApproved; see [ADR-0001](../decisions/0001-adr.md).\n"
    path.write_text(text, encoding="utf-8")

    graph, config = _graph(repo)
    plan = plan_finalize(graph, config, repo, "0007-draft-disposition", env={})
    assert plan.blockers == ()
    descriptions = " | ".join(f.description for f in plan.component_fixes)
    assert "add implements: 0007-draft-disposition to docs/components/auth.md" in descriptions


def test_finalize_blocks_on_a_created_doc_that_was_never_written(repo: Path) -> None:
    path = repo / "docs" / "rfcs" / "0007-draft-disposition.md"
    text = path.read_text(encoding="utf-8")
    text = text.replace("rfc_state: draft", "rfc_state: accepted")
    text = text.replace("status: draft", "status: stable")
    text = text.replace(
        "---\n\n# RFC 0007",
        "resolved_by: docs/decisions/0001-adr.md\nrequired_updates:\n"
        "  - path: docs/components/new-thing.md\n    kind: create\n---\n\n# RFC 0007",
    )
    text += "\n## Resolution\n\nApproved; see [ADR-0001](../decisions/0001-adr.md).\n"
    path.write_text(text, encoding="utf-8")

    graph, config = _graph(repo)
    plan = plan_finalize(graph, config, repo, "0007-draft-disposition", env={})

    assert [b.code for b in plan.blockers] == ["rfc-follow-through/missing-required-update-path"]


def test_finalize_blocks_on_an_unreadable_baseline(repo: Path) -> None:
    """Finalization writes `rfc_state: implemented`; doing that over a baseline nobody can
    read would record a transition `irminsul check` refuses to judge."""
    (repo / ".irminsul-baseline.json").write_text("{not json", encoding="utf-8")
    graph, config = _graph(repo)

    plan = plan_finalize(graph, config, repo, _RFC, bindings=_BINDINGS, env={})

    assert "baseline-unreadable" in {b.code for b in plan.blockers}
    assert not plan.rfc_fixes


_OLD_REQUIREMENT = "Users SHALL be able to authenticate through their company identity provider."
_OWNER_DOC = "docs/components/auth.md"
_RECORD_LINK = "../decisions/0001-adr.md"


def _retire(repo: Path, record: str, *phrases: str) -> None:
    """Make the stable decision record `record` tombstone each phrase as a concept."""
    path = repo / "docs" / "decisions" / f"{record}.md"
    entries = "".join(
        f"  - id: {phrase.replace(' ', '-')}\n    kind: concept\n    matches:\n"
        f"      - {phrase}\n    guidance: Do not name it.\n"
        for phrase in phrases
    )
    text = path.read_text(encoding="utf-8")
    path.write_text(
        text.replace("\n---\n\n#", f"\nretires:\n{entries}---\n\n#", 1), encoding="utf-8"
    )


def _add_record(repo: Path, slug: str, *phrases: str) -> None:
    (repo / "docs" / "decisions" / f"{slug}.md").write_text(
        f"---\nid: {slug}\ntitle: Another record\nstatus: stable\nsummary: Another record.\n"
        "---\n\n# Another record\n\nA second decision record.\n",
        encoding="utf-8",
    )
    _retire(repo, slug, *phrases)


def _require(repo: Path, text: str) -> None:
    path = repo / "docs" / "rfcs" / f"{_RFC}.md"
    path.write_text(
        path.read_text(encoding="utf-8").replace(_OLD_REQUIREMENT, text), encoding="utf-8"
    )


def _plan(repo: Path) -> FinalizePlan:
    graph, config = _graph(repo)
    return plan_finalize(graph, config, repo, _RFC, bindings=_BINDINGS, env={})


def _apply(repo: Path, plan: FinalizePlan) -> None:
    for fixes in (plan.component_fixes, plan.rfc_fixes):
        assert apply_fixes(repo, list(fixes), dry_run=False, confirm=True).errors == []


def _owner_findings(repo: Path) -> list[Finding]:
    graph, _ = _graph(repo)
    return [
        finding
        for finding in RetiredReferencesCheck().run(graph)
        if finding.path is not None and finding.path.as_posix() == _OWNER_DOC
    ]


def test_a_bare_retired_name_in_the_owner_doc_is_reported(repo: Path) -> None:
    """The control: without it the tests below could pass because no tombstone was live."""
    _retire(repo, "0001-adr", "old-code")
    owner = repo / _OWNER_DOC
    owner.write_text(owner.read_text(encoding="utf-8") + "\nNever call old-code.\n", "utf-8")

    assert [finding.data["match"] for finding in _owner_findings(repo)] == ["old-code"]


def test_finalize_links_a_name_the_resolving_record_retires(repo: Path) -> None:
    _retire(repo, "0001-adr", "old-code")
    _require(repo, "Users SHALL NOT see `old-code` after login.")

    plan = _plan(repo)

    assert plan.blockers == ()
    [promotion] = plan.promotions
    assert promotion.text == f"Users SHALL NOT see [`old-code`]({_RECORD_LINK}) after login."
    _apply(repo, plan)
    assert f"[`old-code`]({_RECORD_LINK})" in _graph(repo)[0].nodes["auth"].body
    assert _owner_findings(repo) == []

    again = _plan(repo)
    assert again.blockers == ()
    assert again.component_fixes == ()
    assert again.rfc_fixes == ()


@pytest.mark.parametrize(
    ("requirement", "promoted"),
    [
        ("Prose SHALL NOT name old-code.", f"Prose SHALL NOT name [old-code]({_RECORD_LINK})."),
        (
            "`old-code` and `old-code` SHALL go.",
            f"[`old-code`]({_RECORD_LINK}) and [`old-code`]({_RECORD_LINK}) SHALL go.",
        ),
        ("Legacy Mode SHALL go.", f"[Legacy Mode]({_RECORD_LINK}) SHALL go."),
        (
            f"A cited [`old-code`]({_RECORD_LINK}) SHALL stay as written.",
            f"A cited [`old-code`]({_RECORD_LINK}) SHALL stay as written.",
        ),
        (
            "See https://example.com/old-code for `old-code-v2` SHALL hold.",
            "See https://example.com/old-code for `old-code-v2` SHALL hold.",
        ),
        ("Nothing retired SHALL be named.", "Nothing retired SHALL be named."),
    ],
)
def test_finalize_links_only_what_retired_references_would_report(
    repo: Path, requirement: str, promoted: str
) -> None:
    _retire(repo, "0001-adr", "old-code", "legacy mode")
    _require(repo, requirement)

    plan = _plan(repo)

    assert plan.blockers == ()
    [promotion] = plan.promotions
    assert promotion.text == promoted


@pytest.mark.parametrize(
    "requirement",
    [
        "The `diff/old-code` path SHALL go.",
        "The [old-code docs](https://example.com/x) SHALL go.",
    ],
)
def test_finalize_refuses_a_name_no_link_to_the_record_can_answer(
    repo: Path, requirement: str
) -> None:
    _retire(repo, "0001-adr", "old-code")
    _require(repo, requirement)

    plan = _plan(repo)

    [promotion] = plan.promotions
    assert promotion.text == requirement
    assert [blocker.code for blocker in plan.blockers] == ["promoted-retired-reference"]
    assert plan.component_fixes == ()
    assert plan.rfc_fixes == ()


def test_finalize_leaves_another_records_tombstone_and_refuses(repo: Path) -> None:
    _retire(repo, "0001-adr", "old-code")
    _add_record(repo, "0002-another", "other-code")
    _require(repo, "Users SHALL NOT see `old-code` or `other-code` after login.")

    plan = _plan(repo)

    [promotion] = plan.promotions
    assert promotion.text == (
        f"Users SHALL NOT see [`old-code`]({_RECORD_LINK}) or `other-code` after login."
    )
    [blocker] = plan.blockers
    assert blocker.code == "promoted-retired-reference"
    assert "other-code" in blocker.message
    assert "docs/decisions/0002-another.md" in blocker.message
    assert plan.component_fixes == ()
    assert plan.rfc_fixes == ()


def test_finalize_blocks_on_what_verify_blocks_on(repo: Path) -> None:
    """Finalize had no unknown-component rule and named the check's finding
    `check-error:change-binding`, so verify's blockers did not predict finalize's."""
    path = repo / "docs" / "rfcs" / f"{_RFC}.md"
    path.write_text(
        path.read_text(encoding="utf-8").replace(
            "affects:\n  - auth\n", "affects:\n  - auth\n  - ghost\n"
        ),
        encoding="utf-8",
    )
    graph, config = _graph(repo)

    plan = plan_finalize(graph, config, repo, _RFC, bindings=_BINDINGS, env={})
    verify = build_change_report(repo, config, _RFC, env={}, graph=graph)

    assert "change-binding/unknown-component" in {b.code for b in plan.blockers}
    assert {b.code for b in verify.blockers} <= {b.code for b in plan.blockers}


def test_finalize_blocks_on_a_stale_anchor_in_an_affected_doc(repo: Path) -> None:
    """Verify blocked on a drifted anchor in an affected component doc; finalize did not,
    so it would write `implemented` over it."""
    owner = repo / _OWNER_DOC
    owner.write_text(
        owner.read_text(encoding="utf-8")
        + "\nLogin works.\n<!-- anchor: app/auth/login.py#login @sha256:deadbeef0000 -->\n",
        encoding="utf-8",
    )

    plan = _plan(repo)

    assert "claim-anchor/pinned-drift" in {b.code for b in plan.blockers}
    assert plan.rfc_fixes == ()


def test_finalize_reports_a_missing_decision_record_as_missing_adr(repo: Path) -> None:
    graph, config = _graph(repo)

    plan = plan_finalize(graph, config, repo, "0004-draft-ready", env={})

    codes = {b.code for b in plan.blockers}
    assert "missing-adr" in codes
    assert "unresolved-adr" not in codes


def test_refinalizing_never_blocks_on_the_back_link_it_writes(repo: Path) -> None:
    """An implemented RFC's required-update doc without its `implements` entry is exactly
    what finalization writes, so it is never a blocker."""
    path = repo / "docs" / "rfcs" / "0007-draft-disposition.md"
    text = path.read_text(encoding="utf-8")
    text = text.replace("rfc_state: draft", "rfc_state: implemented")
    text = text.replace("status: draft", "status: stable")
    text = text.replace(
        "---\n\n# RFC 0007",
        f"resolved_by: {_ADR}\nrequired_updates:\n"
        f"  - path: {_OWNER_DOC}\n    kind: update\n---\n\n# RFC 0007",
    )
    text += "\n## Resolution\n\nApproved; see [ADR-0001](../decisions/0001-adr.md).\n"
    path.write_text(text, encoding="utf-8")
    graph, config = _graph(repo)

    plan = plan_finalize(graph, config, repo, "0007-draft-disposition", env={})

    assert plan.blockers == ()
    assert [f.description for f in plan.component_fixes] == [
        f"add implements: 0007-draft-disposition to {_OWNER_DOC}"
    ]
