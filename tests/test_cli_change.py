"""Tests for the `irminsul change` command group."""

from __future__ import annotations

import json
from collections.abc import Callable, Collection
from pathlib import Path

import pytest
from typer.testing import CliRunner

from irminsul.change.transition import plan_transition
from irminsul.cli import app
from irminsul.docgraph import DocGraph

from .conftest import load_graph, seed_repo

runner = CliRunner()

_ADR = "docs/decisions/0001-adr.md"


@pytest.fixture
def repo(fixture_repo: Callable[[str], Path]) -> Path:
    return fixture_repo("soft-change-binding")


def test_change_status_json(repo: Path) -> None:
    result = runner.invoke(
        app,
        ["change", "status", "0001-accepted-good", "--format", "json", "--path", str(repo)],
    )
    assert result.exit_code == 0, result.output
    data = json.loads(result.output)
    assert data["change"] == "0001-accepted-good"
    assert data["state"] == "accepted"
    assert "mechanically_ready_for" in data


def test_change_status_unknown_id(repo: Path) -> None:
    result = runner.invoke(app, ["change", "status", "nope", "--path", str(repo)])
    assert result.exit_code == 2
    assert "no RFC found" in result.output


def test_change_verify_json(repo: Path) -> None:
    result = runner.invoke(
        app,
        ["change", "verify", "0004-draft-ready", "--format", "json", "--path", str(repo)],
    )
    assert result.exit_code == 0, result.output
    data = json.loads(result.output)
    assert isinstance(data["blockers"], list)
    assert isinstance(data["semantic_review"], list)


def test_change_transition_plan_only(repo: Path) -> None:
    rfc = repo / "docs" / "rfcs" / "0004-draft-ready.md"
    before = rfc.read_text(encoding="utf-8")
    result = runner.invoke(
        app,
        [
            "change",
            "transition",
            "0004-draft-ready",
            "accepted",
            "--resolved-by",
            _ADR,
            "--path",
            str(repo),
        ],
    )
    assert result.exit_code == 0, result.output
    assert "--confirm" in result.output
    assert rfc.read_text(encoding="utf-8") == before


def test_change_transition_confirm_applies(repo: Path) -> None:
    rfc = repo / "docs" / "rfcs" / "0004-draft-ready.md"
    result = runner.invoke(
        app,
        [
            "change",
            "transition",
            "0004-draft-ready",
            "accepted",
            "--resolved-by",
            _ADR,
            "--confirm",
            "--path",
            str(repo),
        ],
    )
    assert result.exit_code == 0, result.output
    assert "updated" in result.output
    text = rfc.read_text(encoding="utf-8")
    assert "rfc_state: accepted" in text
    assert "status: stable" in text


def test_change_transition_blocked_exits_one(repo: Path) -> None:
    result = runner.invoke(
        app,
        ["change", "transition", "0001-accepted-good", "accepted", "--path", str(repo)],
    )
    assert result.exit_code == 1
    assert "invalid-transition" in result.output


def test_change_verify_plain_shows_tasks(repo: Path) -> None:
    result = runner.invoke(
        app,
        ["change", "verify", "0001-accepted-good", "--path", str(repo)],
    )
    assert result.exit_code == 0, result.output
    assert "T1 Wire the identity-provider client. (req: sso-login)" in result.output
    assert "source evidence:" in result.output


def test_change_finalize_plan_only(repo: Path) -> None:
    seed_repo(repo, "init")
    rfc = repo / "docs" / "rfcs" / "0001-accepted-good.md"
    before = rfc.read_text(encoding="utf-8")
    result = runner.invoke(
        app,
        [
            "change",
            "finalize",
            "0001-accepted-good",
            "--anchor",
            "sso-login=app/auth/login.py#login",
            "--path",
            str(repo),
        ],
    )
    assert result.exit_code == 0, result.output
    assert "--confirm" in result.output
    assert rfc.read_text(encoding="utf-8") == before


def test_change_finalize_confirm_applies(repo: Path) -> None:
    seed_repo(repo, "init")
    result = runner.invoke(
        app,
        [
            "change",
            "finalize",
            "0001-accepted-good",
            "--anchor",
            "sso-login=app/auth/login.py#login",
            "--anchor",
            "sso-login=tests/test_auth.py#test_login",
            "--confirm",
            "--path",
            str(repo),
        ],
    )
    assert result.exit_code == 0, result.output
    assert "updated" in result.output
    rfc = repo / "docs" / "rfcs" / "0001-accepted-good.md"
    assert "rfc_state: implemented" in rfc.read_text(encoding="utf-8")
    owner = repo / "docs" / "components" / "auth.md"
    assert "**0001-accepted-good#sso-login**" in owner.read_text(encoding="utf-8")


def test_change_finalize_presents_semantic_review(repo: Path) -> None:
    seed_repo(repo, "init")
    result = runner.invoke(
        app,
        [
            "change",
            "finalize",
            "0001-accepted-good",
            "--anchor",
            "sso-login=app/auth/login.py#login",
            "--path",
            str(repo),
        ],
    )
    assert result.exit_code == 0, result.output
    assert "semantic review" in result.output
    assert "task 'T1'" in result.output


def test_change_finalize_blocked_exits_one(repo: Path) -> None:
    seed_repo(repo, "init")
    result = runner.invoke(
        app,
        ["change", "finalize", "0001-accepted-good", "--path", str(repo)],
    )
    assert result.exit_code == 1
    assert "missing-binding" in result.output


def _finalize(repo: Path, *flags: str) -> tuple[int, str]:
    result = runner.invoke(
        app,
        [
            "change",
            "finalize",
            "0001-accepted-good",
            "--anchor",
            "sso-login=app/auth/login.py#login",
            *flags,
            "--path",
            str(repo),
        ],
    )
    return result.exit_code, result.output


@pytest.mark.parametrize("flags", [[], ["--confirm"]])
def test_change_finalize_refuses_a_dirty_tree_and_names_the_paths(
    repo: Path, flags: list[str]
) -> None:
    (repo / ".gitignore").write_text("*.log\n", encoding="utf-8")
    seed_repo(repo, "init")
    rfc = repo / "docs" / "rfcs" / "0001-accepted-good.md"
    before = rfc.read_text(encoding="utf-8")
    for index in range(7):
        (repo / "app" / f"scratch{index}.py").write_text("x = 1\n", encoding="utf-8")
    (repo / "build.log").write_text("ignored\n", encoding="utf-8")

    code, output = _finalize(repo, *flags)

    assert code == 1
    assert "7 path(s) are not committed" in output
    assert "app/scratch0.py" in output and "app/scratch4.py" in output
    assert "app/scratch5.py" not in output
    assert "and 2 more" in output
    assert "build.log" not in output
    assert "Commit or stash first" in output
    assert "-> implemented" not in output
    assert rfc.read_text(encoding="utf-8") == before


def test_change_finalize_refuses_an_edit_to_a_tracked_file(repo: Path) -> None:
    seed_repo(repo, "init")
    login = repo / "app" / "auth" / "login.py"
    login.write_text(login.read_text(encoding="utf-8") + "\n# edited\n", encoding="utf-8")

    code, output = _finalize(repo)

    assert code == 1
    assert "app/auth/login.py" in output


def test_change_finalize_on_a_clean_tree_plans_as_before(repo: Path) -> None:
    seed_repo(repo, "init")

    code, output = _finalize(repo)

    assert code == 0, output
    assert "--confirm" in output
    assert "not committed" not in output


def _report_json(repo: Path, command: str, *flags: str) -> tuple[int, dict | str]:
    result = runner.invoke(
        app,
        ["change", command, "0001-accepted-good", "--format", "json", *flags, "--path", str(repo)],
    )
    return result.exit_code, (json.loads(result.output) if result.exit_code == 0 else result.output)


@pytest.mark.parametrize("command", ["status", "verify"])
def test_change_reports_judge_uncommitted_work_unless_committed_only(
    repo: Path, command: str
) -> None:
    base = seed_repo(repo, "init")
    (repo / "app" / "billing" / "extra.py").write_text("x = 1\n", encoding="utf-8")

    code, default = _report_json(repo, command, "--base-ref", base)
    assert code == 0
    assert default["baseline"]["changed_paths"] == ["app/billing/extra.py"]
    assert "billing" in default["touched_undeclared"]

    code, committed = _report_json(repo, command, "--base-ref", base, "--committed-only")
    assert code == 0
    assert committed["baseline"]["changed_paths"] == []
    assert committed["touched_undeclared"] == []


@pytest.mark.parametrize("command", ["status", "verify"])
def test_change_reports_judge_no_change_for_committed_only_without_a_base(
    repo: Path, command: str
) -> None:
    seed_repo(repo, "init")
    (repo / "app" / "billing" / "extra.py").write_text("x = 1\n", encoding="utf-8")

    code, report = _report_json(repo, command, "--committed-only")

    assert code == 0
    assert report["baseline"] == {"source": "committed", "ref": None, "changed_paths": []}
    plain = runner.invoke(
        app,
        ["change", command, "0001-accepted-good", "--committed-only", "--path", str(repo)],
    )
    assert plain.exit_code == 0, plain.output
    assert "no change is judged and nothing uncommitted is read" in plain.output


def test_change_transition_rejects_implemented_target(repo: Path) -> None:
    result = runner.invoke(
        app,
        ["change", "transition", "0004-draft-ready", "implemented", "--path", str(repo)],
    )
    assert result.exit_code == 2


def test_change_transition_rejected_with_resolved_by_blocks(repo: Path) -> None:
    rfc = repo / "docs" / "rfcs" / "0004-draft-ready.md"
    before = rfc.read_text(encoding="utf-8")
    result = runner.invoke(
        app,
        [
            "change",
            "transition",
            "0004-draft-ready",
            "rejected",
            "--resolved-by",
            _ADR,
            "--confirm",
            "--path",
            str(repo),
        ],
    )
    assert result.exit_code == 1
    assert "unsupported-resolved-by" in result.output
    assert rfc.read_text(encoding="utf-8") == before


def test_change_finalize_runs_the_checks_once(repo: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """`change finalize` built verify's report and then its plan, and each ran every check."""
    from irminsul.checks.adoption_record import AdoptionRecordPass

    seed_repo(repo, "init")
    runs: list[str] = []
    original = AdoptionRecordPass.run

    def counted(self: AdoptionRecordPass, graph: DocGraph, selected: Collection[str]) -> list:
        runs.append("run")
        return original(self, graph, selected)

    monkeypatch.setattr(AdoptionRecordPass, "run", counted, raising=True)
    result = runner.invoke(
        app,
        [
            "change",
            "finalize",
            "0001-accepted-good",
            "--anchor",
            "sso-login=app/auth/login.py#login",
            "--path",
            str(repo),
        ],
    )

    assert result.exit_code == 0, result.output
    assert runs == ["run"]


def _report(repo: Path, command: str, rfc_id: str) -> dict:
    result = runner.invoke(
        app, ["change", command, rfc_id, "--format", "json", "--path", str(repo)]
    )
    assert result.exit_code == 0, result.output
    return json.loads(result.output)


def test_status_of_a_draft_blocks_on_what_its_transition_blocks_on(repo: Path) -> None:
    """Status blocked a draft on errors elsewhere in the tree and on a missing diff baseline,
    neither of which `change transition ... accepted` judges."""
    (repo / ".irminsul-baseline.json").unlink()
    rfc = repo / "docs" / "rfcs" / "0004-draft-ready.md"
    rfc.write_text(
        rfc.read_text(encoding="utf-8").replace(
            "rfc_state: draft\n", f"rfc_state: draft\nresolved_by: {_ADR}\n", 1
        ),
        encoding="utf-8",
    )
    graph = load_graph(repo)

    status = _report(repo, "status", "0004-draft-ready")
    plan = plan_transition(graph, graph.config, "0004-draft-ready", "accepted")

    assert [b["code"] for b in status["blockers"]] == [b.code for b in plan.blockers] == []
    assert status["mechanically_ready_for"] == "accepted"
    verify = _report(repo, "verify", "0004-draft-ready")
    assert "unknown-baseline" in {b["code"] for b in verify["blockers"]}


def test_status_of_an_accepted_rfc_blocks_on_what_finalize_blocks_on(repo: Path) -> None:
    seed_repo(repo, "init")
    (repo / "app" / "billing" / "extra.py").write_text("x = 1\n", encoding="utf-8")

    status = _report(repo, "status", "0001-accepted-good")

    assert status["blockers"] == _report(repo, "verify", "0001-accepted-good")["blockers"]
    assert "unreconciled-scope" in {b["code"] for b in status["blockers"]}


def test_status_of_a_terminal_rfc_reports_no_readiness_blockers(repo: Path) -> None:
    """An implemented RFC has no next step, yet status listed blockers for it."""
    rfc = repo / "docs" / "rfcs" / "0002-accepted-missing-affects.md"
    rfc.write_text(
        rfc.read_text(encoding="utf-8").replace("rfc_state: accepted", "rfc_state: implemented"),
        encoding="utf-8",
    )
    seed_repo(repo, "init")

    status = _report(repo, "status", "0002-accepted-missing-affects")

    assert status["state"] == "implemented"
    assert status["blockers"] == []
    assert status["mechanically_ready_for"] == "none"
