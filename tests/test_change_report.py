"""Unit tests for the change report builder (RFC-0029)."""

from __future__ import annotations

import json
import subprocess
from collections.abc import Callable
from pathlib import Path

import pytest

from irminsul.change.report import (
    ChangeError,
    build_change_report,
    change_report_to_json,
    find_rfc_node,
    format_change_status_plain,
    format_change_verify_plain,
    resolve_change_baseline,
)
from irminsul.config import Checks, IrminsulConfig, find_config, load
from irminsul.docgraph import DocGraph, DocNode, build_graph
from irminsul.frontmatter import AudienceEnum, DocFrontmatter, RfcStateEnum, StatusEnum


@pytest.fixture
def repo(fixture_repo: Callable[[str], Path]) -> Path:
    return fixture_repo("soft-change-binding")


def _git(repo: Path, *args: str) -> None:
    subprocess.run(
        ["git", "-C", str(repo), *args],
        check=True,
        capture_output=True,
        text=True,
    )


def _git_init(repo: Path) -> None:
    _git(repo, "init", "-q")
    _git(repo, "config", "user.email", "test@example.com")
    _git(repo, "config", "user.name", "Test")
    _git(repo, "add", ".")
    _git(repo, "commit", "-q", "-m", "init")


def _set_resolved_by(repo: Path, rfc_id: str, adr: str) -> None:
    path = repo / "docs" / "80-evolution" / "rfcs" / f"{rfc_id}.md"
    text = path.read_text(encoding="utf-8")
    path.write_text(
        text.replace("rfc_state: draft\n", f"rfc_state: draft\nresolved_by: {adr}\n", 1),
        encoding="utf-8",
    )


def test_find_rfc_node_by_id(repo: Path) -> None:
    config = load(find_config(repo))
    graph = build_graph(repo, config)
    node = find_rfc_node(graph, config, "0001-accepted-good")
    assert node.id == "0001-accepted-good"


def test_find_rfc_node_by_number(repo: Path) -> None:
    config = load(find_config(repo))
    graph = build_graph(repo, config)
    assert find_rfc_node(graph, config, "0004").id == "0004-draft-ready"


def test_find_rfc_node_by_unpadded_number(repo: Path) -> None:
    config = load(find_config(repo))
    graph = build_graph(repo, config)
    assert find_rfc_node(graph, config, "4").id == "0004-draft-ready"


def test_find_rfc_node_by_path(repo: Path) -> None:
    config = load(find_config(repo))
    graph = build_graph(repo, config)
    node = find_rfc_node(graph, config, "docs/80-evolution/rfcs/0004-draft-ready.md")
    assert node.id == "0004-draft-ready"


def test_find_rfc_node_unknown_raises(repo: Path) -> None:
    config = load(find_config(repo))
    graph = build_graph(repo, config)
    with pytest.raises(ChangeError) as exc:
        find_rfc_node(graph, config, "nope")
    assert exc.value.code == 2


def test_find_rfc_node_non_rfc_raises(repo: Path) -> None:
    config = load(find_config(repo))
    graph = build_graph(repo, config)
    with pytest.raises(ChangeError):
        find_rfc_node(graph, config, "auth")


def test_baseline_unknown_without_git(repo: Path) -> None:
    baseline = resolve_change_baseline(repo, None, env={})
    assert baseline.source == "unknown"
    assert baseline.changed_paths is None


def test_baseline_base_ref_unresolvable(repo: Path) -> None:
    baseline = resolve_change_baseline(repo, "main", env={})
    assert baseline.source == "unknown"
    assert baseline.ref == "main"
    assert baseline.changed_paths is None


def test_baseline_local_lists_untracked(repo: Path) -> None:
    _git_init(repo)
    (repo / "app" / "auth" / "sso.py").write_text("x = 1\n", encoding="utf-8")
    baseline = resolve_change_baseline(repo, None, env={})
    assert baseline.source == "local"
    assert baseline.changed_paths is not None
    assert "app/auth/sso.py" in baseline.changed_paths


def test_report_accepted_clean_tree_is_ready(repo: Path) -> None:
    _git_init(repo)
    report = build_change_report(repo, load(find_config(repo)), "0001-accepted-good", env={})
    assert report.canonical_state == "accepted"
    assert report.blockers == ()
    assert report.touched_undeclared == ()
    assert report.mechanically_ready_for == "implemented"
    assert report.valid_transitions == ("implemented", "rejected")


def test_report_accepted_undeclared_touch_not_ready(repo: Path) -> None:
    _git_init(repo)
    (repo / "app" / "billing" / "extra.py").write_text("x = 1\n", encoding="utf-8")
    report = build_change_report(repo, load(find_config(repo)), "0001-accepted-good", env={})
    assert "billing" in report.touched_undeclared
    assert report.mechanically_ready_for == "none"
    assert any("billing" in clue.question for clue in report.semantic_review)


def test_report_deleted_undeclared_source_is_touched(repo: Path) -> None:
    _git_init(repo)
    (repo / "app" / "billing" / "invoice.py").unlink()
    report = build_change_report(repo, load(find_config(repo)), "0001-accepted-good", env={})
    assert "billing" in report.touched_undeclared
    assert report.mechanically_ready_for == "none"
    assert any(
        item.kind == "changed-source"
        and item.path == "app/billing/invoice.py"
        and item.component == "billing"
        for item in report.evidence
    )


def test_report_deleted_declared_source_is_evidence(repo: Path) -> None:
    _git_init(repo)
    (repo / "app" / "auth" / "session.py").unlink()
    report = build_change_report(repo, load(find_config(repo)), "0001-accepted-good", env={})
    assert report.blockers == ()
    assert report.footprint is not None
    assert report.footprint.touched["auth"] == ("app/auth/session.py",)
    assert report.footprint.unowned_source == ()
    assert report.declared_untouched == ()
    assert report.touched_undeclared == ()
    assert report.mechanically_ready_for == "implemented"


def test_report_missing_affects_blocks(repo: Path) -> None:
    _git_init(repo)
    report = build_change_report(
        repo, load(find_config(repo)), "0002-accepted-missing-affects", env={}
    )
    assert any(b.code == "missing-affects" for b in report.blockers)
    assert report.mechanically_ready_for == "none"


def test_report_unknown_component_blocks(repo: Path) -> None:
    _git_init(repo)
    report = build_change_report(
        repo, load(find_config(repo)), "0003-draft-unknown-component", env={}
    )
    assert any(b.code == "unknown-component" for b in report.blockers)


def test_report_draft_without_adr_is_not_ready(repo: Path) -> None:
    _git_init(repo)
    report = build_change_report(repo, load(find_config(repo)), "0004-draft-ready", env={})
    assert report.canonical_state == "draft"
    assert any(b.code == "missing-adr" for b in report.blockers)
    assert report.mechanically_ready_for == "none"


def test_report_draft_with_affects_and_adr_ready_for_accepted(repo: Path) -> None:
    _set_resolved_by(repo, "0004-draft-ready", "docs/50-decisions/0001-adr.md")
    _git_init(repo)
    report = build_change_report(repo, load(find_config(repo)), "0004-draft-ready", env={})
    assert report.canonical_state == "draft"
    assert report.blockers == ()
    assert report.mechanically_ready_for == "accepted"
    assert any("transition" in action for action in report.next_actions)


def test_report_unknown_baseline_blocks(repo: Path) -> None:
    report = build_change_report(repo, load(find_config(repo)), "0001-accepted-good", env={})
    assert report.baseline.source == "unknown"
    assert any(b.code == "missing-baseline" for b in report.blockers)
    assert report.mechanically_ready_for == "none"


def test_report_deprecated_state_flagged(tmp_path: Path) -> None:
    fm = DocFrontmatter(
        id="0099-old",
        title="Old",
        audience=AudienceEnum.explanation,
        tier=2,
        status=StatusEnum.stable,
        rfc_state=RfcStateEnum.withdrawn,
    )
    path = Path("docs/80-evolution/rfcs/0099-old.md")
    node = DocNode(id="0099-old", path=path, frontmatter=fm, body="# x")
    config = IrminsulConfig(checks=Checks(hard=[]))
    graph = DocGraph(nodes={"0099-old": node}, by_path={path: node}, config=config)

    report = build_change_report(tmp_path, config, "0099-old", env={}, graph=graph)
    assert report.state == "withdrawn"
    assert report.canonical_state == "rejected"
    assert report.state_deprecated is True
    assert report.valid_transitions == ()


def test_report_requirements_payload(repo: Path) -> None:
    _git_init(repo)
    report = build_change_report(repo, load(find_config(repo)), "0001-accepted-good", env={})
    payload = report.extra["requirements"]
    assert isinstance(payload, dict)
    assert payload["disposition"] is None
    [item] = payload["items"]
    assert item["id"] == "sso-login"
    assert item["global_id"] == "0001-accepted-good#sso-login"
    assert item["provenance"] == "code"
    assert item["scenarios"] == 2
    assert item["binding"] == "planned/unbound"

    data = json.loads(change_report_to_json(report))
    assert data["requirements"]["items"][0]["id"] == "sso-login"


def test_report_accepted_without_requirements_blocks(repo: Path) -> None:
    _git_init(repo)
    report = build_change_report(
        repo, load(find_config(repo)), "0002-accepted-missing-affects", env={}
    )
    assert any(b.code == "missing-requirements" for b in report.blockers)


def test_report_single_scenario_clue(repo: Path) -> None:
    _git_init(repo)
    path = repo / "docs" / "80-evolution" / "rfcs" / "0004-draft-ready.md"
    text = path.read_text(encoding="utf-8")
    marker = "#### Scenario: Unknown address"
    path.write_text(text.split(marker)[0], encoding="utf-8")

    report = build_change_report(repo, load(find_config(repo)), "0004-draft-ready", env={})
    assert any("failure scenario" in clue.question for clue in report.semantic_review)


def test_report_task_evidence(repo: Path) -> None:
    _git_init(repo)
    (repo / "app" / "auth" / "sso.py").write_text("x = 1\n", encoding="utf-8")
    (repo / "tests" / "test_auth.py").write_text(
        "def test_login() -> None:\n    assert 1\n", encoding="utf-8"
    )

    report = build_change_report(repo, load(find_config(repo)), "0001-accepted-good", env={})
    payload = report.extra["tasks"]
    assert isinstance(payload, dict)
    items = payload["items"]
    assert [item["id"] for item in items] == ["T1", "T2", "T3"]
    t1 = items[0]
    assert t1["req"] == "sso-login"
    assert "app/auth/sso.py" in t1["source_evidence"]
    assert "tests/test_auth.py" in t1["test_evidence"]
    assert payload["evidence_measured"] is True
    assert payload["summary"] == {
        "total": 3,
        "with_source_evidence": 3,
        "with_test_evidence": 3,
    }


def test_report_task_without_evidence_gets_clue(repo: Path) -> None:
    _git_init(repo)
    report = build_change_report(repo, load(find_config(repo)), "0001-accepted-good", env={})
    payload = report.extra["tasks"]
    assert isinstance(payload, dict)
    assert payload["evidence_measured"] is True
    assert payload["summary"]["with_source_evidence"] == 0
    assert all(item["review_clue"] for item in payload["items"])
    assert any("task 'T1'" in clue.question for clue in report.semantic_review)


def test_report_task_evidence_unknown_without_baseline(repo: Path) -> None:
    report = build_change_report(repo, load(find_config(repo)), "0001-accepted-good", env={})
    assert report.baseline.changed_paths is None

    payload = report.extra["tasks"]
    assert isinstance(payload, dict)
    assert payload["evidence_measured"] is False
    assert payload["summary"] == {
        "total": 3,
        "with_source_evidence": None,
        "with_test_evidence": None,
    }
    assert all(item["source_evidence"] is None for item in payload["items"])
    assert all(item["test_evidence"] is None for item in payload["items"])
    assert all(item["review_clue"] is None for item in payload["items"])
    assert not any(clue.question.startswith("task '") for clue in report.semantic_review)

    data = json.loads(change_report_to_json(report))
    assert data["tasks"]["summary"]["with_source_evidence"] is None
    assert data["tasks"]["items"][0]["source_evidence"] is None


def test_plain_output_never_shows_measured_zeros_without_baseline(repo: Path) -> None:
    report = build_change_report(repo, load(find_config(repo)), "0001-accepted-good", env={})
    status = format_change_status_plain(report)
    verify = format_change_verify_plain(report)

    assert "tasks: 3 declared; evidence unknown (no diff baseline)" in status
    assert "0/3" not in status
    assert "source evidence: unknown (no diff baseline)" in verify
    assert "test evidence:   unknown (no diff baseline)" in verify
    assert "source evidence: none" not in verify


def test_report_unreferenced_task_clue_names_declared_components(repo: Path) -> None:
    _git_init(repo)
    path = repo / "docs" / "80-evolution" / "rfcs" / "0001-accepted-good.md"
    text = path.read_text(encoding="utf-8")
    path.write_text(
        text.replace(
            "- `T3` Refresh the auth component doc. (component: auth)",
            "- `T3` Refresh the auth component doc.",
        ),
        encoding="utf-8",
    )

    report = build_change_report(repo, load(find_config(repo)), "0001-accepted-good", env={})
    payload = report.extra["tasks"]
    assert isinstance(payload, dict)
    clue = payload["items"][2]["review_clue"]
    assert "declared affected component" in clue
    assert "requirement" not in clue.split("(")[0]


def test_report_json_round_trips(repo: Path) -> None:
    _git_init(repo)
    report = build_change_report(repo, load(find_config(repo)), "0001-accepted-good", env={})
    data = json.loads(change_report_to_json(report))
    assert data["version"] == 1
    assert data["change"] == "0001-accepted-good"
    assert data["state"] == "accepted"
    assert isinstance(data["blockers"], list)
    assert isinstance(data["evidence"], list)
    assert isinstance(data["semantic_review"], list)
    assert data["baseline"]["source"] == "local"
    assert data["mechanically_ready_for"] == "implemented"
