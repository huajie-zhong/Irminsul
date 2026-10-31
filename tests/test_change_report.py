"""Unit tests for the change report builder."""

from __future__ import annotations

import json
from collections.abc import Callable
from pathlib import Path

import pytest

import irminsul.change.report as report_module
from irminsul.change.report import (
    ChangeError,
    TaskSummary,
    build_change_report,
    change_report_to_json,
    find_rfc_node,
    format_change_status_plain,
    format_change_verify_plain,
    resolve_change_baseline,
)
from irminsul.config import find_config, load
from irminsul.docgraph import build_graph
from irminsul.git.reader import GitReader

from .conftest import load_graph, seed_repo


@pytest.fixture
def repo(fixture_repo: Callable[[str], Path]) -> Path:
    return fixture_repo("soft-change-binding")


def _set_resolved_by(repo: Path, rfc_id: str, adr: str) -> None:
    path = repo / "docs" / "rfcs" / f"{rfc_id}.md"
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


def test_find_rfc_node_by_path(repo: Path) -> None:
    config = load(find_config(repo))
    graph = build_graph(repo, config)
    node = find_rfc_node(graph, config, "docs/rfcs/0004-draft-ready.md")
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
    baseline = resolve_change_baseline(GitReader(), repo, None, env={})
    assert baseline.source == "unknown"
    assert baseline.changed_paths is None


def test_baseline_base_ref_unresolvable(repo: Path) -> None:
    baseline = resolve_change_baseline(GitReader(), repo, "main", env={})
    assert baseline.source == "unknown"
    assert baseline.ref == "main"
    assert baseline.changed_paths is None


def test_baseline_local_lists_untracked(repo: Path) -> None:
    seed_repo(repo, "init")
    (repo / "app" / "auth" / "sso.py").write_text("x = 1\n", encoding="utf-8")
    baseline = resolve_change_baseline(GitReader(), repo, None, env={})
    assert baseline.source == "local"
    assert baseline.changed_paths is not None
    assert "app/auth/sso.py" in baseline.changed_paths


def test_a_base_ref_baseline_includes_uncommitted_work(repo: Path) -> None:
    base = seed_repo(repo, "init")
    (repo / "app" / "auth" / "sso.py").write_text("x = 1\n", encoding="utf-8")
    (repo / "app" / "auth" / "session.py").unlink()

    for baseline in (
        resolve_change_baseline(GitReader(), repo, base, env={}),
        resolve_change_baseline(GitReader(), repo, None, env={"IRMINSUL_BASE_REF": base}),
        resolve_change_baseline(GitReader(), repo, None, env={"GITHUB_BASE_REF": base}),
    ):
        assert baseline.ref == base
        assert baseline.changed_paths == ("app/auth/session.py", "app/auth/sso.py")


def test_committed_only_leaves_uncommitted_work_out_of_the_baseline(repo: Path) -> None:
    base = seed_repo(repo, "init")
    (repo / "app" / "auth" / "sso.py").write_text("x = 1\n", encoding="utf-8")

    baseline = resolve_change_baseline(GitReader(), repo, base, env={}, committed_only=True)

    assert baseline.source == "base-ref"
    assert baseline.changed_paths == ()


def test_committed_only_without_a_base_ends_the_range_where_it_starts(repo: Path) -> None:
    seed_repo(repo, "init")
    (repo / "app" / "auth" / "sso.py").write_text("x = 1\n", encoding="utf-8")

    baseline = resolve_change_baseline(GitReader(), repo, None, env={}, committed_only=True)

    assert baseline.source == "committed"
    assert baseline.ref is None
    assert baseline.changed_paths == ()


def test_committed_only_reaches_the_graph_the_report_is_judged_on(
    repo: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    seed_repo(repo, "init")
    seen: list[bool] = []
    real_build_graph = report_module.build_graph

    def spy(*args: object, **kwargs: object) -> object:
        seen.append(bool(kwargs.get("committed_only", False)))
        return real_build_graph(*args, **kwargs)  # type: ignore[arg-type]

    monkeypatch.setattr(report_module, "build_graph", spy)
    config = load(find_config(repo))

    build_change_report(repo, config, "0001-accepted-good", env={}, committed_only=True)

    assert seen == [True]


def test_the_local_baseline_of_a_project_below_its_git_root_is_project_relative(
    tmp_path: Path, fixture_repo: Callable[[str], Path]
) -> None:
    mono = tmp_path / "mono"
    project = mono / "proj"
    project.parent.mkdir()
    fixture_repo("soft-change-binding").rename(project)
    seed_repo(mono, "init")
    (project / "app" / "auth" / "sso.py").write_text("x = 1\n", encoding="utf-8")
    (mono / "elsewhere.py").write_text("y = 1\n", encoding="utf-8")

    baseline = resolve_change_baseline(GitReader(), project, None, env={})

    assert baseline.source == "local"
    assert baseline.changed_paths == ("app/auth/sso.py",)


def test_verify_counts_an_uncommitted_file_in_its_footprint(repo: Path) -> None:
    base = seed_repo(repo, "init")
    (repo / "app" / "billing" / "extra.py").write_text("x = 1\n", encoding="utf-8")
    config = load(find_config(repo))

    default = build_change_report(repo, config, "0001-accepted-good", base_ref=base, env={})
    committed = build_change_report(
        repo, config, "0001-accepted-good", base_ref=base, env={}, committed_only=True
    )

    assert "billing" in default.touched_undeclared
    assert any(item.path == "app/billing/extra.py" for item in default.evidence)
    assert committed.touched_undeclared == ()
    assert committed.baseline.changed_paths == ()


def test_report_accepted_clean_tree_is_ready(repo: Path) -> None:
    seed_repo(repo, "init")
    report = build_change_report(repo, load(find_config(repo)), "0001-accepted-good", env={})
    assert report.blockers == ()
    assert report.touched_undeclared == ()
    assert report.mechanically_ready_for == "implemented"
    assert report.valid_transitions == ("implemented", "rejected")


def test_report_accepted_undeclared_touch_not_ready(repo: Path) -> None:
    seed_repo(repo, "init")
    (repo / "app" / "billing" / "extra.py").write_text("x = 1\n", encoding="utf-8")
    report = build_change_report(repo, load(find_config(repo)), "0001-accepted-good", env={})
    assert "billing" in report.touched_undeclared
    assert report.mechanically_ready_for == "none"
    assert any("billing" in clue.question for clue in report.semantic_review)


def test_report_deleted_undeclared_source_is_touched(repo: Path) -> None:
    seed_repo(repo, "init")
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
    seed_repo(repo, "init")
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
    seed_repo(repo, "init")
    report = build_change_report(
        repo, load(find_config(repo)), "0002-accepted-missing-affects", env={}
    )
    assert any(b.code == "change-binding/missing-affects" for b in report.blockers)
    assert report.mechanically_ready_for == "none"


def test_report_unknown_component_blocks(repo: Path) -> None:
    seed_repo(repo, "init")
    report = build_change_report(
        repo, load(find_config(repo)), "0003-draft-unknown-component", env={}
    )
    assert any(b.code == "change-binding/unknown-component" for b in report.blockers)


def test_report_draft_without_adr_is_not_ready(repo: Path) -> None:
    seed_repo(repo, "init")
    report = build_change_report(repo, load(find_config(repo)), "0004-draft-ready", env={})
    assert any(b.code == "missing-adr" for b in report.blockers)
    assert report.mechanically_ready_for == "none"


def test_report_draft_with_affects_and_adr_ready_for_accepted(repo: Path) -> None:
    _set_resolved_by(repo, "0004-draft-ready", "docs/decisions/0001-adr.md")
    seed_repo(repo, "init")
    report = build_change_report(repo, load(find_config(repo)), "0004-draft-ready", env={})
    assert report.blockers == ()
    assert report.mechanically_ready_for == "accepted"
    assert any("transition" in action for action in report.next_actions)


def test_report_unknown_baseline_blocks(repo: Path) -> None:
    report = build_change_report(repo, load(find_config(repo)), "0001-accepted-good", env={})
    assert report.baseline.source == "unknown"
    assert any(b.code == "unknown-baseline" for b in report.blockers)
    assert report.mechanically_ready_for == "none"


def test_report_requirements_payload(repo: Path) -> None:
    seed_repo(repo, "init")
    report = build_change_report(repo, load(find_config(repo)), "0001-accepted-good", env={})
    assert report.requirements is not None
    assert report.requirements.disposition is None
    [item] = report.requirements.items
    assert item.id == "sso-login"
    assert item.global_id == "0001-accepted-good#sso-login"
    assert item.provenance == "code"
    assert item.scenarios == 2
    assert item.binding == "planned/unbound"

    data = json.loads(change_report_to_json(report))
    assert data["requirements"]["items"][0]["id"] == "sso-login"


def test_report_accepted_without_requirements_blocks(repo: Path) -> None:
    seed_repo(repo, "init")
    report = build_change_report(
        repo, load(find_config(repo)), "0002-accepted-missing-affects", env={}
    )
    assert any(b.code == "missing-requirements" for b in report.blockers)


def test_report_single_scenario_clue(repo: Path) -> None:
    seed_repo(repo, "init")
    path = repo / "docs" / "rfcs" / "0004-draft-ready.md"
    text = path.read_text(encoding="utf-8")
    marker = "#### Scenario: Unknown address"
    path.write_text(text.split(marker)[0], encoding="utf-8")

    report = build_change_report(repo, load(find_config(repo)), "0004-draft-ready", env={})
    assert any("failure scenario" in clue.question for clue in report.semantic_review)


def test_report_task_evidence(repo: Path) -> None:
    seed_repo(repo, "init")
    (repo / "app" / "auth" / "sso.py").write_text("x = 1\n", encoding="utf-8")
    (repo / "tests" / "test_auth.py").write_text(
        "def test_login() -> None:\n    assert 1\n", encoding="utf-8"
    )

    report = build_change_report(repo, load(find_config(repo)), "0001-accepted-good", env={})
    tasks = report.tasks
    assert tasks is not None
    assert [(item.id, item.req) for item in tasks.items] == [
        ("T1", "sso-login"),
        ("T2", "sso-login"),
        ("T3", None),
    ]
    assert tasks.summary == TaskSummary(total=3)


def test_the_changed_files_are_named_once_for_the_rfc_not_per_task(repo: Path) -> None:
    seed_repo(repo, "init")
    (repo / "app" / "auth" / "sso.py").write_text("x = 1\n", encoding="utf-8")
    (repo / "tests" / "test_auth.py").write_text(
        "def test_login() -> None:\n    assert 1\n", encoding="utf-8"
    )

    report = build_change_report(repo, load(find_config(repo)), "0001-accepted-good", env={})
    verify = format_change_verify_plain(report)

    assert verify.count("app/auth/sso.py") == 1
    assert verify.count("tests/test_auth.py") == 1
    assert "source evidence" not in verify
    assert "with changed tests" not in verify
    assert verify.index("changed-source: app/auth/sso.py") < verify.index("  tasks: 3 declared")
    assert "    T1 Wire the identity-provider client. (req: sso-login)" in verify


def test_one_rfc_clue_asks_about_the_tests_not_one_per_task(repo: Path) -> None:
    seed_repo(repo, "init")
    (repo / "app" / "auth" / "sso.py").write_text("x = 1\n", encoding="utf-8")
    (repo / "tests" / "test_auth.py").write_text(
        "def test_login() -> None:\n    assert 1\n", encoding="utf-8"
    )

    report = build_change_report(repo, load(find_config(repo)), "0001-accepted-good", env={})

    questions = [clue.question for clue in report.semantic_review]
    assert (
        questions.count("confirm the changed tests assert each task's scenario, and run them") == 1
    )
    assert not any(question.startswith("task '") for question in questions)


def test_a_declared_component_with_no_changed_source_is_still_a_clue(repo: Path) -> None:
    seed_repo(repo, "init")

    report = build_change_report(repo, load(find_config(repo)), "0001-accepted-good", env={})

    assert any(
        "declared component 'auth' has no implementation evidence" in clue.question
        for clue in report.semantic_review
    )


def test_no_task_gets_a_clue_of_its_own_when_nothing_changed(repo: Path) -> None:
    seed_repo(repo, "init")
    report = build_change_report(repo, load(find_config(repo)), "0001-accepted-good", env={})

    assert not any(clue.question.startswith("task '") for clue in report.semantic_review)
    assert report.tasks is not None
    assert report.tasks.summary == TaskSummary(total=3)


def test_report_tasks_are_listed_without_a_baseline(repo: Path) -> None:
    report = build_change_report(repo, load(find_config(repo)), "0001-accepted-good", env={})
    assert report.baseline.changed_paths is None

    assert report.tasks is not None
    assert report.tasks.summary == TaskSummary(total=3)
    assert not any("confirm the changed tests" in clue.question for clue in report.semantic_review)

    data = json.loads(change_report_to_json(report))
    assert data["evidence_measured"] is False
    assert data["tasks"]["summary"] == {"total": 3}
    assert set(data["tasks"]["items"][0]) == {"id", "text", "req", "component"}


def test_plain_output_never_shows_measured_zeros_without_baseline(repo: Path) -> None:
    report = build_change_report(repo, load(find_config(repo)), "0001-accepted-good", env={})
    status = format_change_status_plain(report)
    verify = format_change_verify_plain(report)

    assert "  tasks: 3 declared" in status
    assert "0/3" not in status
    assert "  evidence: unknown (no diff baseline)" in verify
    assert "evidence: (none)" not in verify


def test_report_json_round_trips(repo: Path) -> None:
    seed_repo(repo, "init")
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


def test_an_unreadable_baseline_is_a_blocker_not_silence(repo: Path) -> None:
    """The gate read a baseline it could not load as no baseline at all, so the report
    blocked on everything the file records without ever saying the file was the problem,
    while `irminsul check` refuses to run over it."""
    seed_repo(repo, "init")
    (repo / ".irminsul-baseline.json").write_text("{not json", encoding="utf-8")

    report = build_change_report(repo, load(find_config(repo)), "0001-accepted-good", env={})

    unreadable = [b for b in report.blockers if b.code == "baseline-unreadable"]
    assert len(unreadable) == 1
    assert unreadable[0].path == ".irminsul-baseline.json"
    assert "could not read baseline" in unreadable[0].message
    assert report.mechanically_ready_for == "none"


def test_baselined_debt_never_blocks_a_transition(repo: Path) -> None:
    """The fixture's baseline records two certain `change-binding` findings on other RFCs.
    They would not fail `irminsul check`, so they do not block this RFC either."""
    seed_repo(repo, "init")

    report = build_change_report(repo, load(find_config(repo)), "0001-accepted-good", env={})

    recorded = {
        ("change-binding/missing-affects", "docs/rfcs/0002-accepted-missing-affects.md"),
        ("change-binding/unknown-component", "docs/rfcs/0003-draft-unknown-component.md"),
    }
    assert not recorded & {(b.code, b.path) for b in report.blockers}
    (repo / ".irminsul-baseline.json").unlink()
    unbaselined = build_change_report(repo, load(find_config(repo)), "0001-accepted-good", env={})
    assert recorded <= {(b.code, b.path) for b in unbaselined.blockers}


def test_an_unreadable_baseline_costs_no_second_run(
    repo: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The gate ran every check twice over a baseline it could not read: once to find the
    file unreadable and again without it. The baseline is a step after the run."""
    from collections.abc import Collection

    from irminsul.change.gate import gate_run
    from irminsul.checks import Finding
    from irminsul.checks.adoption_record import AdoptionRecordPass
    from irminsul.docgraph import DocGraph

    runs: list[str] = []

    def counted(self, graph: DocGraph, selected: Collection[str]) -> list[Finding]:
        runs.append("run")
        return []

    monkeypatch.setattr(AdoptionRecordPass, "run", counted, raising=True)
    (repo / ".irminsul-baseline.json").write_text("{not json", encoding="utf-8")

    gates = gate_run(load_graph(repo))

    assert [b.code for b in gates.blockers] == ["baseline-unreadable"]
    assert runs == ["run"]


def _rfc_path(repo: Path, rfc_id: str) -> Path:
    return repo / "docs" / "rfcs" / f"{rfc_id}.md"


def test_a_rule_the_gate_judges_blocks_once_under_its_finding_code(repo: Path) -> None:
    """The report raised its own `missing-affects` and repeated the check's finding as
    `check-error:change-binding`, so one missing field read as two blockers."""
    seed_repo(repo, "init")
    (repo / ".irminsul-baseline.json").unlink()

    report = build_change_report(
        repo, load(find_config(repo)), "0002-accepted-missing-affects", env={}
    )

    rfc = "docs/rfcs/0002-accepted-missing-affects.md"
    about_affects = [b for b in report.blockers if b.path == rfc and "`affects`" in b.message]
    assert [b.code for b in about_affects] == ["change-binding/missing-affects"]


def test_a_draft_warning_the_gate_raises_is_not_repeated(repo: Path) -> None:
    """A draft's unknown component was a blocker, a `check-error:` blocker and a scoped
    finding at once."""
    seed_repo(repo, "init")
    (repo / ".irminsul-baseline.json").unlink()

    report = build_change_report(
        repo, load(find_config(repo)), "0003-draft-unknown-component", env={}
    )

    assert [b.code for b in report.blockers if "'ghost'" in b.message] == [
        "change-binding/unknown-component"
    ]
    assert not [s for s in report.scoped_findings if s.check == "change-binding"]


def test_verify_blocks_on_the_unreconciled_scope_finalize_refuses(repo: Path) -> None:
    """Verify said "not ready" without a blocker for a touched-but-undeclared component,
    while finalize refused with `unreconciled-scope`."""
    seed_repo(repo, "init")
    (repo / "app" / "billing" / "extra.py").write_text("x = 1\n", encoding="utf-8")

    report = build_change_report(repo, load(find_config(repo)), "0001-accepted-good", env={})

    assert "unreconciled-scope" in {b.code for b in report.blockers}
    assert report.mechanically_ready_for == "none"


def test_a_draft_report_blocks_on_the_affects_acceptance_needs(repo: Path) -> None:
    """A draft without `affects` was never ready for acceptance, yet no blocker said why."""
    path = _rfc_path(repo, "0004-draft-ready")
    path.write_text(
        path.read_text(encoding="utf-8").replace("affects:\n  - auth\n", ""), encoding="utf-8"
    )
    _set_resolved_by(repo, "0004-draft-ready", "docs/decisions/0001-adr.md")
    seed_repo(repo, "init")

    report = build_change_report(repo, load(find_config(repo)), "0004-draft-ready", env={})

    [missing] = [b for b in report.blockers if b.code == "change-binding/missing-affects"]
    assert missing.message.startswith("accepted RFC does not declare `affects`")
    assert report.mechanically_ready_for == "none"


def test_another_rfcs_finding_that_quotes_this_id_does_not_block_it(repo: Path) -> None:
    """The report took an `rfc-follow-through` finding as this RFC's when its message quoted
    the id, so another RFC's required update named `0001-accepted-good` blocked this one."""
    other = _rfc_path(repo, "0002-accepted-missing-affects")
    other.write_text(
        other.read_text(encoding="utf-8").replace(
            "required_updates: []\n",
            "required_updates:\n  - path: 0001-accepted-good\n    kind: update\n",
        ),
        encoding="utf-8",
    )
    seed_repo(repo, "init")

    report = build_change_report(repo, load(find_config(repo)), "0001-accepted-good", env={})

    assert report.blockers == ()
    assert report.mechanically_ready_for == "implemented"


def test_change_report_accepts_an_absolute_path(repo: Path) -> None:
    report = build_change_report(
        repo, load(find_config(repo)), str(_rfc_path(repo, "0004-draft-ready")), env={}
    )
    assert report.change == "0004-draft-ready"


def test_a_grammar_warning_the_gate_raises_is_not_also_a_scoped_finding(repo: Path) -> None:
    """A draft's requirement-grammar warnings were blockers and, again, findings about this
    change."""
    config = repo / "irminsul.toml"
    config.write_text(
        config.read_text(encoding="utf-8").replace(
            '    "change-binding",\n', '    "change-binding",\n    "requirement-grammar",\n'
        ),
        encoding="utf-8",
    )
    seed_repo(repo, "init")

    report = build_change_report(repo, load(find_config(repo)), "0005-draft-bad-grammar", env={})

    assert "requirement-grammar/missing-id" in {b.code for b in report.blockers}
    assert not [s for s in report.scoped_findings if s.check == "requirement-grammar"]
