"""Tests for `irminsul context`."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest
from typer.testing import CliRunner

import irminsul.context as context_module
import irminsul.git.changes as changes_module
from irminsul.cli import app

runner = CliRunner()


def _make_context_repo(tmp_path: Path, *, configured_soft: bool = True) -> Path:
    repo = tmp_path / "ctx"
    repo.mkdir()
    checks = "" if configured_soft else "\n[checks]\nsoft_deterministic = []\n"
    (repo / "irminsul.toml").write_text(
        "\n".join(
            [
                'project_name = "ctx"',
                "[paths]",
                'docs_root = "docs"',
                'source_roots = ["src"]',
                checks,
                "",
            ]
        ),
        encoding="utf-8",
    )

    src = repo / "src" / "mylib"
    src.mkdir(parents=True)
    (src / "core.py").write_text("from mylib import helper\n\ndef run(): pass\n", encoding="utf-8")
    (src / "core_extra.py").write_text("def run_more(): pass\n", encoding="utf-8")
    (src / "helper.py").write_text("def help(): pass\n", encoding="utf-8")

    tests = repo / "tests"
    tests.mkdir()
    (tests / "test_core.py").write_text("def test_core(): pass\n", encoding="utf-8")
    (tests / "test_helper.py").write_text("def test_helper(): pass\n", encoding="utf-8")

    docs = repo / "docs" / "20-components"
    docs.mkdir(parents=True)
    (docs / "core.md").write_text(
        "\n".join(
            [
                "---",
                "id: core",
                'title: "Core"',
                "audience: explanation",
                "tier: 3",
                "status: stable",
                "depends_on:",
                "  - helper",
                "describes:",
                "  - src/mylib/core.py",
                "  - src/mylib/core_extra.py",
                "tests:",
                "  - tests/test_core.py",
                "---",
                "",
                "# Core",
                "",
                "Owns the core module.",
                "",
            ]
        ),
        encoding="utf-8",
    )
    (docs / "helper.md").write_text(
        "\n".join(
            [
                "---",
                "id: helper",
                'title: "Helper"',
                "audience: explanation",
                "tier: 3",
                "status: stable",
                "describes:",
                "  - src/mylib/helper.py",
                "tests:",
                "  - tests/test_helper.py",
                "---",
                "",
                "# Helper",
                "",
                "Owns the helper module.",
                "",
            ]
        ),
        encoding="utf-8",
    )
    (docs / "core-note.md").write_text(
        "\n".join(
            [
                "---",
                "id: core-note",
                'title: "Core Note"',
                "audience: explanation",
                "tier: 2",
                "status: draft",
                "describes: []",
                "---",
                "",
                "# Core Note",
                "",
            ]
        ),
        encoding="utf-8",
    )
    return repo


def _add_active_rfc(repo: Path) -> None:
    rfcs = repo / "docs" / "80-evolution" / "rfcs"
    rfcs.mkdir(parents=True)
    (rfcs / "0001-retry.md").write_text(
        "\n".join(
            [
                "---",
                "id: 0001-retry",
                'title: "Retry semantics"',
                "audience: explanation",
                "tier: 2",
                "status: draft",
                "describes: []",
                "rfc_state: draft",
                "affects:",
                "  - core",
                "---",
                "",
                "# Retry semantics",
                "",
                "## Requirements",
                "",
                "### Requirement: Bounded retries",
                "ID: bounded-retries",
                "Provenance: code",
                "",
                "The client MUST stop after the configured retry limit.",
                "",
            ]
        ),
        encoding="utf-8",
    )


def _git(repo: Path, *args: str) -> None:
    subprocess.run(["git", "-C", str(repo), *args], check=True, capture_output=True, text=True)


def test_context_source_path_json_returns_owner_tests_and_dependencies(tmp_path: Path) -> None:
    repo = _make_context_repo(tmp_path)

    result = runner.invoke(
        app,
        ["context", "src/mylib/core.py", "--format", "json", "--path", str(repo)],
    )

    assert result.exit_code == 0, result.output
    data = json.loads(result.output)
    assert set(data) == {"version", "mode", "results", "unmatched"}
    assert data["version"] == 1
    assert data["mode"] == "path"
    assert data["unmatched"] == []
    [context] = data["results"]
    assert context["owner"]["id"] == "core"
    assert context["source_claims"] == ["src/mylib/core.py"]
    assert context["entrypoint"] == "src/mylib/core.py"
    assert context["tests"] == ["tests/test_core.py"]
    assert [doc["id"] for doc in context["depends_on"]] == ["helper"]
    assert "irminsul check --profile hard" in context["hints"]


def test_context_doc_path_plain_returns_doc_metadata(tmp_path: Path) -> None:
    repo = _make_context_repo(tmp_path)

    result = runner.invoke(app, ["context", "docs/20-components/core.md", "--path", str(repo)])

    assert result.exit_code == 0, result.output
    assert "owner: core (docs/20-components/core.md)" in result.output
    assert "source claims: src/mylib/core.py" in result.output
    assert "tests: tests/test_core.py" in result.output
    assert "depends_on: helper (docs/20-components/helper.md)" in result.output


def test_context_before_edit_groups_paths_and_surfaces_active_change(tmp_path: Path) -> None:
    repo = _make_context_repo(tmp_path)
    _add_active_rfc(repo)

    result = runner.invoke(
        app,
        [
            "context",
            "--before-edit",
            "src/mylib/core.py",
            "src/mylib/core_extra.py",
            "--format",
            "json",
            "--path",
            str(repo),
        ],
    )

    assert result.exit_code == 0, result.output
    data = json.loads(result.output)
    assert data["mode"] == "path"
    assert data["workflow"] == "before-edit"
    assert data["validation"]["hard_checks_passed"] is True
    [context] = data["results"]
    assert context["input"] == ["src/mylib/core.py", "src/mylib/core_extra.py"]
    assert context["owner"]["id"] == "core"
    assert context["source_claims"] == ["src/mylib/core.py", "src/mylib/core_extra.py"]
    assert context["active_changes"] == [
        {
            "id": "0001-retry",
            "title": "Retry semantics",
            "path": "docs/80-evolution/rfcs/0001-retry.md",
            "state": "draft",
            "requirements": [{"id": "bounded-retries", "title": "Bounded retries"}],
        }
    ]
    assert data["next_actions"] == [
        {
            "command": "irminsul change status 0001-retry",
            "reason": "Active RFC explicitly affects component 'core'.",
        },
        {
            "command": "irminsul context --after-edit",
            "reason": "Validate the working tree and affected repository knowledge after editing.",
        },
    ]
    assert all(
        finding["check"] != "orphans" for item in data["results"] for finding in item["findings"]
    )


def test_context_before_edit_plain_encodes_workflow(tmp_path: Path) -> None:
    repo = _make_context_repo(tmp_path)
    _add_active_rfc(repo)

    result = runner.invoke(
        app,
        ["context", "--before-edit", "src/mylib/core.py", "--path", str(repo)],
    )

    assert result.exit_code == 0, result.output
    assert "Workflow: before-edit" in result.output
    assert "0001-retry [draft]" in result.output
    assert "requirements: bounded-retries" in result.output
    assert "irminsul context --after-edit" in result.output


def test_context_after_edit_runs_global_hard_validation(tmp_path: Path) -> None:
    repo = _make_context_repo(tmp_path)
    _git(repo, "init")
    _git(repo, "config", "user.email", "dev@example.com")
    _git(repo, "config", "user.name", "Dev")
    _git(repo, "add", ".")
    _git(repo, "commit", "-m", "initial")
    (repo / "docs" / "20-components" / "broken.md").write_text(
        "# Missing frontmatter\n", encoding="utf-8"
    )

    result = runner.invoke(
        app,
        ["context", "--after-edit", "--format", "json", "--path", str(repo)],
    )

    assert result.exit_code == 1, result.output
    data = json.loads(result.output)
    assert data["mode"] == "changed"
    assert data["workflow"] == "after-edit"
    assert data["results"] == []
    assert data["validation"]["hard_checks_passed"] is False
    assert data["validation"]["errors"] > 0
    assert data["next_actions"][-1] == {
        "command": "irminsul check --profile hard",
        "reason": "The repository hard gate has errors to resolve.",
    }
    assert all(
        action["command"] != "irminsul list undocumented --all" for action in data["next_actions"]
    )


def test_context_after_edit_routes_declared_test_changes(tmp_path: Path) -> None:
    repo = _make_context_repo(tmp_path)
    _git(repo, "init")
    _git(repo, "config", "user.email", "dev@example.com")
    _git(repo, "config", "user.name", "Dev")
    _git(repo, "add", ".")
    _git(repo, "commit", "-m", "initial")
    (repo / "tests" / "test_core.py").write_text("def test_core_more(): pass\n", encoding="utf-8")

    result = runner.invoke(
        app,
        ["context", "--after-edit", "--format", "json", "--path", str(repo)],
    )

    assert result.exit_code == 0, result.output
    data = json.loads(result.output)
    assert data["unmatched"] == []
    [context] = data["results"]
    assert context["owner"]["id"] == "core"
    assert context["input"] == ["tests/test_core.py"]


def test_context_topic_sorts_exact_id_first(tmp_path: Path) -> None:
    repo = _make_context_repo(tmp_path)

    result = runner.invoke(
        app,
        ["context", "--topic", "core", "--format", "json", "--path", str(repo)],
    )

    assert result.exit_code == 0, result.output
    data = json.loads(result.output)
    assert [item["owner"]["id"] for item in data["results"]][:2] == ["core", "core-note"]


def test_context_profile_all_available_broadens_deterministic_findings(tmp_path: Path) -> None:
    repo = _make_context_repo(tmp_path, configured_soft=False)

    configured = runner.invoke(
        app,
        ["context", "src/mylib/core.py", "--format", "json", "--path", str(repo)],
    )
    broad = runner.invoke(
        app,
        [
            "context",
            "src/mylib/core.py",
            "--profile",
            "all-available",
            "--format",
            "json",
            "--path",
            str(repo),
        ],
    )

    assert configured.exit_code == 0, configured.output
    assert broad.exit_code == 0, broad.output
    configured_checks = {
        finding["check"]
        for result in json.loads(configured.output)["results"]
        for finding in result["findings"]
    }
    broad_checks = {
        finding["check"]
        for result in json.loads(broad.output)["results"]
        for finding in result["findings"]
    }
    assert "orphans" not in configured_checks
    assert "orphans" in broad_checks


def test_context_changed_groups_by_owner_and_reports_unmatched(tmp_path: Path) -> None:
    repo = _make_context_repo(tmp_path)
    _git(repo, "init")
    _git(repo, "config", "user.email", "dev@example.com")
    _git(repo, "config", "user.name", "Dev")
    _git(repo, "add", ".")
    _git(repo, "commit", "-m", "initial")

    (repo / "src" / "mylib" / "core.py").write_text("from mylib import helper\n", encoding="utf-8")
    (repo / "src" / "mylib" / "helper.py").write_text("def help_more(): pass\n", encoding="utf-8")
    _git(repo, "add", "src/mylib/helper.py")
    (repo / "src" / "mylib" / "new.py").write_text("def new(): pass\n", encoding="utf-8")

    result = runner.invoke(app, ["context", "--changed", "--format", "json", "--path", str(repo)])

    assert result.exit_code == 0, result.output
    data = json.loads(result.output)
    assert data["mode"] == "changed"
    assert [item["owner"]["id"] for item in data["results"]] == ["core", "helper"]
    assert data["unmatched"] == [
        {
            "path": "src/mylib/new.py",
            "reason": "no owning doc found",
            "candidates": [],
        }
    ]


def test_context_changed_normalizes_monorepo_subfolder_paths(tmp_path: Path) -> None:
    mono = tmp_path / "mono"
    mono.mkdir()
    repo = _make_context_repo(mono)
    (mono / "outside.py").write_text("print('outside')\n", encoding="utf-8")
    _git(mono, "init")
    _git(mono, "config", "user.email", "dev@example.com")
    _git(mono, "config", "user.name", "Dev")
    _git(mono, "add", ".")
    _git(mono, "commit", "-m", "initial")

    (repo / "src" / "mylib" / "core.py").write_text("def run(): pass\n", encoding="utf-8")
    (mono / "outside.py").write_text("print('changed outside')\n", encoding="utf-8")

    result = runner.invoke(app, ["context", "--changed", "--format", "json", "--path", str(repo)])

    assert result.exit_code == 0, result.output
    data = json.loads(result.output)
    assert data["unmatched"] == []
    [context] = data["results"]
    assert context["owner"]["id"] == "core"
    assert context["input"] == ["src/mylib/core.py"]


def test_git_changed_paths_parses_nul_porcelain_special_paths(tmp_path: Path, monkeypatch) -> None:
    class Result:
        def __init__(self, stdout: str) -> None:
            self.returncode = 0
            self.stdout = stdout
            self.stderr = ""

    def fake_run(args, **kwargs):
        if args[-1] == "--show-prefix":
            return Result("")
        assert "-z" in args
        assert args[-2:] == ["--", "."]
        return Result(
            " M src/tab\tfile.py\0?? src/back\\slash.py\0R  src/new name.py\0src/old name.py\0"
        )

    monkeypatch.setattr(changes_module.subprocess, "run", fake_run)

    assert context_module._git_changed_paths(tmp_path) == [
        "src/back\\slash.py",
        "src/new name.py",
        "src/tab\tfile.py",
    ]


def test_git_changed_paths_strips_worktree_prefix(tmp_path: Path, monkeypatch) -> None:
    class Result:
        def __init__(self, stdout: str) -> None:
            self.returncode = 0
            self.stdout = stdout
            self.stderr = ""

    def fake_run(args, **kwargs):
        if args[-1] == "--show-prefix":
            return Result("project/docs/\n")
        return Result(
            " M project/docs/src/mylib/core.py\0"
            "?? project/docs/src/mylib/new.py\0"
            " M other-project/outside.py\0"
        )

    monkeypatch.setattr(changes_module.subprocess, "run", fake_run)

    assert context_module._git_changed_paths(tmp_path) == [
        "src/mylib/core.py",
        "src/mylib/new.py",
    ]


def test_git_changed_paths_reports_missing_git(tmp_path: Path, monkeypatch) -> None:
    def fake_run(args, **kwargs):
        raise FileNotFoundError("git")

    monkeypatch.setattr(changes_module.subprocess, "run", fake_run)

    with pytest.raises(context_module.ContextError, match="git command not found"):
        context_module._git_changed_paths(tmp_path)


def test_context_changed_reports_rename_destination_only(tmp_path: Path) -> None:
    repo = _make_context_repo(tmp_path)
    _git(repo, "init")
    _git(repo, "config", "user.email", "dev@example.com")
    _git(repo, "config", "user.name", "Dev")
    _git(repo, "add", ".")
    _git(repo, "commit", "-m", "initial")
    _git(repo, "mv", "src/mylib/core.py", "src/mylib/core-renamed.py")

    result = runner.invoke(app, ["context", "--changed", "--format", "json", "--path", str(repo)])

    assert result.exit_code == 0, result.output
    data = json.loads(result.output)
    assert data["unmatched"] == [
        {
            "path": "src/mylib/core-renamed.py",
            "reason": "no owning doc found",
            "candidates": [],
        }
    ]


def test_context_rejects_invalid_combinations(tmp_path: Path) -> None:
    repo = _make_context_repo(tmp_path)

    result = runner.invoke(
        app, ["context", "src/mylib/core.py", "--topic", "core", "--path", str(repo)]
    )

    assert result.exit_code == 2
    assert "choose exactly one input mode" in result.output

    missing_before_target = runner.invoke(app, ["context", "--before-edit", "--path", str(repo)])
    assert missing_before_target.exit_code == 2
    assert "--before-edit requires one or more paths" in missing_before_target.output

    after_with_target = runner.invoke(
        app,
        ["context", "--after-edit", "src/mylib/core.py", "--path", str(repo)],
    )
    assert after_with_target.exit_code == 2
    assert "--after-edit cannot be combined" in after_with_target.output

    multiple_without_workflow = runner.invoke(
        app,
        [
            "context",
            "src/mylib/core.py",
            "src/mylib/helper.py",
            "--path",
            str(repo),
        ],
    )
    assert multiple_without_workflow.exit_code == 2
    assert "multiple paths require the --before-edit workflow" in multiple_without_workflow.output


def test_context_missing_path_is_nonzero(tmp_path: Path) -> None:
    repo = _make_context_repo(tmp_path)

    result = runner.invoke(app, ["context", "src/mylib/missing.py", "--path", str(repo)])

    assert result.exit_code == 1
    assert "path does not exist" in result.output


def test_context_no_topic_matches_returns_empty_json(tmp_path: Path) -> None:
    repo = _make_context_repo(tmp_path)

    result = runner.invoke(
        app,
        ["context", "--topic", "absent", "--format", "json", "--path", str(repo)],
    )

    assert result.exit_code == 0, result.output
    data = json.loads(result.output)
    assert data["mode"] == "topic"
    assert data["results"] == []
    assert data["unmatched"] == []


def test_context_unmatched_hint_points_at_list_undocumented_all() -> None:
    report = context_module.ContextReport(
        version=1,
        mode="changed",
        results=[],
        unmatched=[
            context_module.UnmatchedPath(
                path="src/mylib/new.py",
                reason="no owning doc found",
                candidates=[],
            )
        ],
    )

    plain = context_module.format_context_plain(report)

    assert "hint: irminsul list undocumented --all" in plain


def test_context_changed_flags_doc_not_co_changed(tmp_path: Path) -> None:
    repo = _make_context_repo(tmp_path)
    _git(repo, "init")
    _git(repo, "config", "user.email", "dev@example.com")
    _git(repo, "config", "user.name", "Dev")
    _git(repo, "add", ".")
    _git(repo, "commit", "-m", "initial")

    # Touch a source file but not its owning doc.
    (repo / "src" / "mylib" / "core.py").write_text("def run(): return 1\n", encoding="utf-8")

    json_result = runner.invoke(
        app, ["context", "--changed", "--format", "json", "--path", str(repo)]
    )
    assert json_result.exit_code == 0, json_result.output
    core = next(
        item for item in json.loads(json_result.output)["results"] if item["owner"]["id"] == "core"
    )
    assert core["doc_co_changed"] is False

    plain_result = runner.invoke(app, ["context", "--changed", "--path", str(repo)])
    assert "owning doc not updated in this change" in plain_result.output

    # Now also update the owning doc; the gap closes.
    doc = repo / "docs" / "20-components" / "core.md"
    doc.write_text(doc.read_text(encoding="utf-8") + "\nUpdated.\n", encoding="utf-8")

    json_result = runner.invoke(
        app, ["context", "--changed", "--format", "json", "--path", str(repo)]
    )
    assert json_result.exit_code == 0, json_result.output
    core = next(
        item for item in json.loads(json_result.output)["results"] if item["owner"]["id"] == "core"
    )
    assert core["doc_co_changed"] is True
