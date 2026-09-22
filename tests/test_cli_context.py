"""Tests for `irminsul context`."""

from __future__ import annotations

import json
import re
import subprocess
from collections.abc import Callable
from pathlib import Path

import pytest
from typer.testing import CliRunner

import irminsul.context as context_module
import irminsul.git.changes as changes_module
from irminsul.cli import app

runner = CliRunner()


def _make_context_repo(
    tmp_path: Path,
    *,
    configured_soft: bool = True,
    claim_count: int = 1,
) -> Path:
    repo = tmp_path / "ctx"
    repo.mkdir()
    checks = "" if configured_soft else "\n[checks]\nenabled = []\n"
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

    docs = repo / "docs" / "components"
    docs.mkdir(parents=True)
    claim_lines = ["claims:"]
    for index in range(claim_count):
        claim_lines.extend(
            [
                f"  - id: core-contract-{index + 1}",
                "    state: implemented",
                "    kind: invariant",
                f"    claim: Core invariant {index + 1} remains true.",
                "    evidence:",
                "      - src/mylib/core.py",
            ]
        )
    (docs / "core.md").write_text(
        "\n".join(
            [
                "---",
                "id: core",
                'title: "Core"',
                "status: stable",
                "depends_on:",
                "  - helper",
                *claim_lines,
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
                "## Scope & Limitations",
                "",
                "Does not own the helper.",
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
                "## Scope & Limitations",
                "",
                "Does not own the core.",
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


def _make_topic_repo(tmp_path: Path) -> Path:
    repo = tmp_path / "topic"
    repo.mkdir()
    (repo / "irminsul.toml").write_text(
        "\n".join(
            [
                'project_name = "topic"',
                "[paths]",
                'docs_root = "docs"',
                'source_roots = ["src"]',
                "",
            ]
        ),
        encoding="utf-8",
    )

    docs = repo / "docs" / "components"
    docs.mkdir(parents=True)
    (docs / "widget.md").write_text(
        "\n".join(
            [
                "---",
                "id: widget",
                'title: "Widget assembly"',
                "status: stable",
                "summary: Deterministic pipeline for building widgets.",
                "describes: []",
                "---",
                "",
                "# Widget assembly",
                "",
            ]
        ),
        encoding="utf-8",
    )
    (docs / "pipeline.md").write_text(
        "\n".join(
            [
                "---",
                "id: pipeline",
                'title: "Batch runner"',
                "status: stable",
                "summary: Executes each stage in order.",
                "tags:",
                "  - widget",
                "describes: []",
                "---",
                "",
                "# Batch runner",
                "",
            ]
        ),
        encoding="utf-8",
    )
    (docs / "combo.md").write_text(
        "\n".join(
            [
                "---",
                "id: combo",
                'title: "Combo doc"',
                "status: stable",
                "summary: Uses a widget pipeline for staging.",
                "describes: []",
                "---",
                "",
                "# Combo doc",
                "",
            ]
        ),
        encoding="utf-8",
    )
    return repo


def _add_active_rfc(repo: Path) -> None:
    rfcs = repo / "docs" / "rfcs"
    rfcs.mkdir(parents=True)
    # A draft RFC still needs an inbound link: being unfinished does not make being
    # an orphan a lesser finding.
    core = repo / "docs" / "components" / "core.md"
    core.write_text(
        core.read_text(encoding="utf-8") + "\nSee [retry semantics](../rfcs/0001-retry.md).\n",
        encoding="utf-8",
    )
    (rfcs / "0001-retry.md").write_text(
        "\n".join(
            [
                "---",
                "id: 0001-retry",
                'title: "Retry semantics"',
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


def _link_core(repo: Path) -> None:
    """Link the two docs to each other, so the repo reports no errors.

    Being a draft does not excuse `core-note` from being an orphan: an orphan is a
    statement about the tree around a doc, not about the doc being unfinished.
    """
    docs = repo / "docs" / "components"
    note = docs / "core-note.md"
    note.write_text(note.read_text(encoding="utf-8") + "\nSee [core](core.md).\n", encoding="utf-8")
    core = docs / "core.md"
    core.write_text(
        core.read_text(encoding="utf-8") + "\nSee [the note](core-note.md).\n", encoding="utf-8"
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
    assert set(data) == {"version", "mode", "results", "unmatched", "claim_reviews"}
    assert data["version"] == 1
    assert data["mode"] == "path"
    assert data["unmatched"] == []
    [context] = data["results"]
    assert context["owner"]["id"] == "core"
    assert context["source_claims"] == ["src/mylib/core.py"]
    assert context["entrypoint"] == "src/mylib/core.py"
    assert context["tests"] == ["tests/test_core.py"]
    assert [doc["id"] for doc in context["depends_on"]] == ["helper"]
    assert "irminsul check" in context["hints"]


def test_context_hints_offer_fix_for_fixable_finding(
    fixture_repo: Callable[[str], Path],
) -> None:
    repo = fixture_repo("soft-glossary")

    result = runner.invoke(
        app,
        [
            "context",
            "docs/components/composer.md",
            "--format",
            "json",
            "--path",
            str(repo),
        ],
    )

    assert result.exit_code == 0, result.output
    [context] = json.loads(result.output)["results"]
    assert context["hints"] == [
        "irminsul fix --check glossary-discipline --confirm",
        "irminsul check",
    ]


def test_context_hints_are_gate_only_without_fixable_finding(tmp_path: Path) -> None:
    repo = _make_context_repo(tmp_path)

    result = runner.invoke(
        app,
        [
            "context",
            "src/mylib/core.py",
            "--format",
            "json",
            "--path",
            str(repo),
        ],
    )

    assert result.exit_code == 0, result.output
    [context] = json.loads(result.output)["results"]
    assert context["hints"] == ["irminsul check"]


def test_context_doc_path_plain_returns_doc_metadata(tmp_path: Path) -> None:
    repo = _make_context_repo(tmp_path)

    result = runner.invoke(app, ["context", "docs/components/core.md", "--path", str(repo)])

    assert result.exit_code == 0, result.output
    assert "owner: core (docs/components/core.md)" in result.output
    assert "source claims: src/mylib/core.py" in result.output
    assert "tests: tests/test_core.py" in result.output
    assert "depends_on: helper (docs/components/helper.md)" in result.output


def test_context_before_edit_groups_paths_and_surfaces_active_change(tmp_path: Path) -> None:
    repo = _make_context_repo(tmp_path)
    _add_active_rfc(repo)
    _link_core(repo)

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
    # Nothing was checked, so nothing may read as checked — and the key an older reader
    # would have consulted is absent rather than True.
    assert data["validation"]["repository"] == {
        "state": "not_run",
        "errors": None,
        "warnings": None,
    }
    assert data["validation"]["change"]["state"] == "not_run"
    assert "checks_passed" not in data["validation"]
    [context] = data["results"]
    assert context["input"] == ["src/mylib/core.py", "src/mylib/core_extra.py"]
    assert context["owner"]["id"] == "core"
    assert context["source_claims"] == ["src/mylib/core.py", "src/mylib/core_extra.py"]
    assert context["active_changes"] == {
        "shown": [
            {
                "id": "0001-retry",
                "title": "Retry semantics",
                "path": "docs/rfcs/0001-retry.md",
                "state": "draft",
                "requirements": [{"id": "bounded-retries", "title": "Bounded retries"}],
            }
        ],
        "omitted": 0,
        "omitted_ids": [],
        "retrieve": None,
    }
    assert context["content"] == {
        "included": [
            {
                "category": "owner",
                "doc_id": "core",
                "path": "docs/components/core.md",
                "title": "Core",
                "text": "Owns the core module.",
                "reason": "Owns the requested path through document 'core'.",
                "truncated": False,
            },
            {
                "category": "boundary",
                "doc_id": "core",
                "path": "docs/components/core.md",
                "title": "Scope & Limitations (Core)",
                "text": (
                    "Does not own the helper.\n\n"
                    "See [retry semantics](../rfcs/0001-retry.md).\n\n"
                    "See [the note](core-note.md)."
                ),
                "reason": "What the owning document says this component does not do.",
                "truncated": False,
            },
            # core-contract-1 cites src/mylib/core.py, one of the requested paths, so it
            # is queued under claim_reviews and not excerpted here as well.
            {
                "category": "requirements",
                "doc_id": "0001-retry",
                "path": "docs/rfcs/0001-retry.md",
                "title": "Requirement bounded-retries: Bounded retries",
                "text": "The client MUST stop after the configured retry limit.",
                "reason": "Active RFC '0001-retry' explicitly affects owner 'core'.",
                "truncated": False,
            },
        ],
        "omitted": {"owner": 0, "boundary": 0, "claims": 0, "requirements": 0},
    }
    assert [review["claim_id"] for review in data["claim_reviews"]] == ["core-contract-1"]
    assert data["next_actions"] == [
        {
            "command": "irminsul context docs/components/core.md",
            "reason": (
                "These paths are evidence for claim 'core-contract-1'; read the document "
                "that declares it and decide whether claim and code still agree."
            ),
        },
        {
            "command": "irminsul change status 0001-retry",
            "reason": "Active RFC explicitly affects component 'core'.",
        },
        {
            "command": "irminsul context --after-edit",
            "reason": "Validate the working tree and affected repository knowledge after editing.",
        },
    ]
    # `null`, not `[]`: before-edit ran no checks, and an empty list would read as a
    # clean bill of health for a file nobody has looked at yet.
    assert all(item["findings"] is None for item in data["results"])


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
    assert "[owner] Core (docs/components/core.md)" in result.output
    assert "Owns the core module." in result.output
    assert "The client MUST stop after the configured retry limit." in result.output
    assert "irminsul context --after-edit" in result.output


def test_context_include_expands_dependencies_on_primitive_lookup(tmp_path: Path) -> None:
    repo = _make_context_repo(tmp_path)

    result = runner.invoke(
        app,
        [
            "context",
            "src/mylib/core.py",
            "--include",
            "owner,dependencies",
            "--format",
            "json",
            "--path",
            str(repo),
        ],
    )

    assert result.exit_code == 0, result.output
    [context] = json.loads(result.output)["results"]
    assert [item["category"] for item in context["content"]["included"]] == [
        "owner",
        "dependencies",
    ]
    assert context["content"]["included"][1]["doc_id"] == "helper"
    assert context["content"]["included"][1]["text"] == "Owns the helper module."


def test_context_include_none_and_unknown_category(tmp_path: Path) -> None:
    repo = _make_context_repo(tmp_path)

    none_result = runner.invoke(
        app,
        [
            "context",
            "--before-edit",
            "src/mylib/core.py",
            "--include",
            "none",
            "--format",
            "json",
            "--path",
            str(repo),
        ],
    )
    assert none_result.exit_code == 0, none_result.output
    [context] = json.loads(none_result.output)["results"]
    assert context["content"] == {"included": [], "omitted": {}}

    invalid_result = runner.invoke(
        app,
        [
            "context",
            "src/mylib/core.py",
            "--include",
            "semantic-ranking",
            "--path",
            str(repo),
        ],
    )
    assert invalid_result.exit_code == 2
    assert "unknown --include categories" in invalid_result.output
    assert "all" not in invalid_result.output
    assert "none" not in invalid_result.output


def test_context_content_reports_fixed_count_omissions(tmp_path: Path) -> None:
    # core_extra.py has the same owner but is cited by none of the claims, so they stay
    # content excerpts and the count bound is what decides which survive.
    repo = _make_context_repo(tmp_path, claim_count=10)

    result = runner.invoke(
        app,
        [
            "context",
            "--before-edit",
            "src/mylib/core_extra.py",
            "--include",
            "claims",
            "--format",
            "json",
            "--path",
            str(repo),
        ],
    )

    assert result.exit_code == 0, result.output
    [context] = json.loads(result.output)["results"]
    assert len(context["content"]["included"]) == 8
    assert context["content"]["omitted"] == {"claims": 2}


def test_context_after_edit_runs_global_hard_validation(tmp_path: Path) -> None:
    repo = _make_context_repo(tmp_path)
    _git(repo, "init")
    _git(repo, "config", "user.email", "dev@example.com")
    _git(repo, "config", "user.name", "Dev")
    _git(repo, "add", ".")
    _git(repo, "commit", "-m", "initial")
    (repo / "docs" / "components" / "broken.md").write_text(
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
    assert data["validation"]["repository"]["state"] == "failed"
    assert data["validation"]["repository"]["errors"] > 0
    assert data["validation"]["checks_passed"] is False
    # The broken doc is this edit's, so the change verdict names it rather than leaving
    # the agent to work out which half of the repository's errors it is answerable for.
    assert data["validation"]["change"]["state"] == "failed"
    assert data["validation"]["change"]["new_errors"] > 0
    assert data["next_actions"][-1] == {
        "command": "irminsul check",
        "reason": "This change introduced errors.",
    }
    assert all(
        action["command"] != "irminsul list undocumented --all" for action in data["next_actions"]
    )


def test_context_after_edit_routes_declared_test_changes(tmp_path: Path) -> None:
    repo = _make_context_repo(tmp_path)
    _link_core(repo)
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


def test_context_plain_findings_render_code_as_identity(tmp_path: Path) -> None:
    """Plain findings carry the `[<code>]` identity `irminsul explain` accepts,
    with severity kept visible — the same convention `irminsul check` prints —
    not the old `[severity/check]` bracket."""
    repo = _make_context_repo(tmp_path, configured_soft=False)

    result = runner.invoke(
        app,
        [
            "context",
            "src/mylib/core.py",
            "--profile",
            "all-available",
            "--path",
            str(repo),
        ],
    )

    assert result.exit_code == 0, result.output
    assert re.search(r"(?m)^\s+error\s+\[orphans/orphan-doc\] ", result.output), result.output
    assert "[warning/orphans]" not in result.output


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
            "governed_by": [],
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
            "governed_by": [],
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


def test_context_topic_multi_word_matches_terms_across_fields(tmp_path: Path) -> None:
    repo = _make_topic_repo(tmp_path)

    result = runner.invoke(
        app,
        ["context", "--topic", "widget pipeline", "--format", "json", "--path", str(repo)],
    )

    assert result.exit_code == 0, result.output
    data = json.loads(result.output)
    # "pipeline" doc only carries "widget" via its tags and "pipeline" via its
    # id/path, so it only matches when terms are allowed to hit different fields.
    assert "pipeline" in {item["owner"]["id"] for item in data["results"]}


def test_context_topic_multi_word_missing_term_returns_none(tmp_path: Path) -> None:
    repo = _make_topic_repo(tmp_path)

    result = runner.invoke(
        app,
        ["context", "--topic", "widget zzz-nope", "--format", "json", "--path", str(repo)],
    )

    assert result.exit_code == 0, result.output
    data = json.loads(result.output)
    assert data["results"] == []


def test_context_topic_multi_word_ranks_phrase_hit_then_field_breadth(tmp_path: Path) -> None:
    repo = _make_topic_repo(tmp_path)

    result = runner.invoke(
        app,
        ["context", "--topic", "widget pipeline", "--format", "json", "--path", str(repo)],
    )

    assert result.exit_code == 0, result.output
    data = json.loads(result.output)
    # "combo" wins on its literal "widget pipeline" phrase hit in summary;
    # "widget" then outranks "pipeline" on distinct-field breadth (4 vs 3).
    assert [item["owner"]["id"] for item in data["results"]] == ["combo", "widget", "pipeline"]


def test_context_topic_normalizes_whitespace_without_changing_ranking(tmp_path: Path) -> None:
    repo = _make_topic_repo(tmp_path)

    normal = runner.invoke(
        app,
        ["context", "--topic", "widget pipeline", "--format", "json", "--path", str(repo)],
    )
    spaced = runner.invoke(
        app,
        ["context", "--topic", "widget  pipeline", "--format", "json", "--path", str(repo)],
    )

    assert normal.exit_code == 0, normal.output
    assert spaced.exit_code == 0, spaced.output
    normal_ids = [item["owner"]["id"] for item in json.loads(normal.output)["results"]]
    spaced_ids = [item["owner"]["id"] for item in json.loads(spaced.output)["results"]]
    assert spaced_ids == normal_ids


def test_context_topic_ranks_separator_equivalent_id_first(tmp_path: Path) -> None:
    repo = _make_topic_repo(tmp_path)
    doc = repo / "docs" / "components" / "widget-pipeline.md"
    doc.write_text(
        "\n".join(
            [
                "---",
                "id: widget-pipeline",
                'title: "Assembly flow"',
                "status: stable",
                "describes: []",
                "---",
                "",
                "# Assembly flow",
                "",
            ]
        ),
        encoding="utf-8",
    )

    result = runner.invoke(
        app,
        ["context", "--topic", "widget pipeline", "--format", "json", "--path", str(repo)],
    )

    assert result.exit_code == 0, result.output
    data = json.loads(result.output)
    assert data["results"][0]["owner"]["id"] == "widget-pipeline"


def test_context_topic_help_describes_quoted_keyword_search() -> None:
    result = runner.invoke(app, ["context", "--help"], terminal_width=160)

    assert result.exit_code == 0, result.output
    # Rich may colour and wrap the help whatever width is asked for, as it does in CI.
    plain = re.sub(r"\x1b\[[0-9;]*m", "", result.output)
    text = " ".join(re.sub(r"[│╭╮╰╯─]", " ", plain).split())
    assert "quoted topic" in text
    assert "keywords; every" in text
    assert re.search(r"whitespace-\s*separated term", text)
    assert "must match" in text


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
    doc = repo / "docs" / "components" / "core.md"
    doc.write_text(doc.read_text(encoding="utf-8") + "\nUpdated.\n", encoding="utf-8")

    json_result = runner.invoke(
        app, ["context", "--changed", "--format", "json", "--path", str(repo)]
    )
    assert json_result.exit_code == 0, json_result.output
    core = next(
        item for item in json.loads(json_result.output)["results"] if item["owner"]["id"] == "core"
    )
    assert core["doc_co_changed"] is True


def test_an_rfc_naming_the_owner_in_required_updates_is_active(tmp_path: Path) -> None:
    repo = _make_context_repo(tmp_path)
    _add_active_rfc(repo)
    rfc = repo / "docs" / "rfcs" / "0001-retry.md"
    text = rfc.read_text(encoding="utf-8")
    rfc.write_text(
        text.replace(
            "affects:\n  - core\n",
            "required_updates:\n  - path: docs/components/core.md\n    kind: update\n",
        ),
        encoding="utf-8",
    )

    result = runner.invoke(
        app,
        ["context", "--before-edit", "src/mylib/core.py", "--path", str(repo)],
    )

    assert result.exit_code == 0, result.output
    assert "0001-retry [draft]" in result.output


def test_before_edit_surfaces_the_owning_doc_scope_and_limitations(tmp_path: Path) -> None:
    """The boundary the owning doc draws travels with the file, not just its summary."""
    repo = _make_context_repo(tmp_path)
    _link_core(repo)

    result = runner.invoke(
        app,
        ["context", "--before-edit", "src/mylib/helper.py", "--path", str(repo)],
    )

    assert result.exit_code == 0, result.output
    assert "[boundary] Scope & Limitations (Helper)" in result.output
    assert "Does not own the core." in result.output


def test_boundary_is_absent_when_the_owning_doc_draws_none(tmp_path: Path) -> None:
    repo = _make_context_repo(tmp_path)
    _link_core(repo)
    helper = repo / "docs" / "components" / "helper.md"
    helper.write_text(
        helper.read_text(encoding="utf-8").replace(
            "\n## Scope & Limitations\n\nDoes not own the core.\n", ""
        ),
        encoding="utf-8",
    )

    result = runner.invoke(
        app,
        [
            "context",
            "--before-edit",
            "src/mylib/helper.py",
            "--format",
            "json",
            "--path",
            str(repo),
        ],
    )

    assert result.exit_code == 0, result.output
    [context] = json.loads(result.output)["results"]
    assert [item["category"] for item in context["content"]["included"]] == ["owner"]


def test_an_unowned_file_still_reports_the_claims_that_govern_it(tmp_path: Path) -> None:
    """No `describes:` glob covers `deploy.yml`, but a claim cites it as evidence.

    Reporting the claim is not the same as inventing an owner: the file is still
    unmatched, and the packet still says so.
    """
    repo = _make_context_repo(tmp_path)
    _link_core(repo)
    (repo / "deploy.yml").write_text("steps: []\n", encoding="utf-8")
    doc = repo / "docs" / "components" / "core.md"
    doc.write_text(
        doc.read_text(encoding="utf-8").replace(
            "describes:\n",
            "\n".join(
                [
                    "  - id: deploy-calls-the-cli",
                    "    state: implemented",
                    "    kind: invariant",
                    "    relation: governs-evidence",
                    "    claim: Deployment installs the CLI and calls it; logic belongs in the CLI.",
                    "    evidence:",
                    "      - deploy.yml",
                    "describes:",
                    "",
                ]
            ),
        ),
        encoding="utf-8",
    )

    result = runner.invoke(
        app,
        ["context", "--before-edit", "deploy.yml", "--format", "json", "--path", str(repo)],
    )

    data = json.loads(result.output)
    [unmatched] = data["unmatched"]
    assert unmatched["path"] == "deploy.yml"
    assert unmatched["reason"] == "no owning doc found"
    assert unmatched["governed_by"] == [
        {
            "doc": {
                "id": "core",
                "title": "Core",
                "path": "docs/components/core.md",
                "status": "stable",
            },
            "claim_id": "deploy-calls-the-cli",
            "relation": "governs-evidence",
            "claim": "Deployment installs the CLI and calls it; logic belongs in the CLI.",
        }
    ]

    # A governs-evidence claim is shown once, in the richer claims block; the terse
    # `governed by` line under Unmatched is for the relations that block leaves out.
    plain = runner.invoke(app, ["context", "--before-edit", "deploy.yml", "--path", str(repo)])
    assert "governed by deploy-calls-the-cli" not in plain.output
    assert "deploy-calls-the-cli (governs-evidence) in docs/components/core.md" in plain.output


def test_a_follows_evidence_claim_shows_under_the_unmatched_path(tmp_path: Path) -> None:
    """The one relation the review block leaves out keeps the terse `governed by` line."""
    repo = _make_context_repo(tmp_path)
    _link_core(repo)
    (repo / "deploy.yml").write_text("steps: []\n", encoding="utf-8")
    doc = repo / "docs" / "components" / "core.md"
    doc.write_text(
        doc.read_text(encoding="utf-8").replace(
            "describes:\n",
            "\n".join(
                [
                    "  - id: deploy-mirrors-the-cli",
                    "    state: implemented",
                    "    kind: invariant",
                    "    relation: follows-evidence",
                    "    claim: Deployment mirrors what the CLI does.",
                    "    evidence:",
                    "      - deploy.yml",
                    "describes:",
                    "",
                ]
            ),
        ),
        encoding="utf-8",
    )

    plain = runner.invoke(app, ["context", "--before-edit", "deploy.yml", "--path", str(repo)])

    assert "governed by deploy-mirrors-the-cli (follows-evidence)" in plain.output
    assert "Governing claims over these paths" not in plain.output


def _make_governing_claim(repo: Path) -> None:
    """Turn the core claim into a contract, and record the decision behind it.

    The claim cites `src/mylib/core.py`, which `core.md` owns, and `src/mylib/helper.py`,
    which it does not: a contract is written against code wherever that code lives.
    """
    decisions = repo / "docs" / "decisions"
    decisions.mkdir(parents=True)
    (decisions / "0001-core-is-pure.md").write_text(
        "\n".join(
            [
                "---",
                "id: 0001-core-is-pure",
                'title: "Core stays pure"',
                "status: stable",
                "describes: []",
                "---",
                "",
                "# ADR-0001: Core stays pure",
                "",
                "## Status",
                "",
                "Accepted.",
                "",
                "## Context",
                "",
                "Core kept growing state.",
                "",
                "## Decision",
                "",
                "It holds none.",
                "",
                "## Alternatives Considered",
                "",
                "A cache keyed by call.",
                "",
                "## Consequences",
                "",
                "Every call re-derives.",
                "",
            ]
        ),
        encoding="utf-8",
    )
    doc = repo / "docs" / "components" / "core.md"
    text = doc.read_text(encoding="utf-8")
    text = text.replace(
        "    kind: invariant\n",
        "    kind: invariant\n    relation: governs-evidence\n",
    ).replace(
        "    evidence:\n      - src/mylib/core.py\n",
        "    evidence:\n      - src/mylib/core.py\n      - src/mylib/helper.py\n",
    )
    doc.write_text(
        text
        + "\nCore holds no state, as [ADR-0001](../decisions/0001-core-is-pure.md)\n"
        + "decided. <!-- claim:core-contract-1 -->\n",
        encoding="utf-8",
    )


def test_changing_only_code_still_queues_the_governing_claim_for_review(tmp_path: Path) -> None:
    """The gap this closes: the contract's document was left untouched, and checks pass.

    Nothing here says the claim is broken. What the packet says is that the change
    reached the code the claim is written against, which is a question for a reader.
    """
    repo = _make_context_repo(tmp_path)
    _link_core(repo)
    _make_governing_claim(repo)
    _git(repo, "init")
    _git(repo, "config", "user.email", "dev@example.com")
    _git(repo, "config", "user.name", "Dev")
    _git(repo, "add", ".")
    _git(repo, "commit", "-m", "initial")

    (repo / "src" / "mylib" / "core.py").write_text("CACHE = {}\n", encoding="utf-8")

    result = runner.invoke(
        app, ["context", "--after-edit", "--format", "json", "--path", str(repo)]
    )

    data = json.loads(result.output)
    [review] = data["claim_reviews"]
    assert review["claim_id"] == "core-contract-1"
    assert review["relation"] == "governs-evidence"
    assert review["doc"]["path"] == "docs/components/core.md"
    assert review["evidence"] == ["src/mylib/core.py"]
    assert [doc["path"] for doc in review["decisions"]] == ["docs/decisions/0001-core-is-pure.md"]
    assert review["tests"] == ["tests/test_core.py"]
    assert "Core invariant 1 remains true." in review["claim"]
    assert "src/mylib/core.py" in review["question"]

    # The owning doc was never edited, and the tree still passes.
    assert data["validation"]["checks_passed"] is True
    assert "docs/components/core.md" not in {
        path for item in data["results"] for path in item["input"]
    }

    plain = runner.invoke(app, ["context", "--after-edit", "--path", str(repo)])
    assert "Claims to review — this change touched their evidence:" in plain.output
    assert "This is a question for you, not a finding" in plain.output
    assert any(
        action["reason"].startswith("This change touched evidence for governing claim")
        for action in data["next_actions"]
    )


def test_a_governing_claim_surfaces_for_evidence_its_own_doc_does_not_own(
    tmp_path: Path,
) -> None:
    repo = _make_context_repo(tmp_path)
    _link_core(repo)
    _make_governing_claim(repo)

    result = runner.invoke(
        app,
        [
            "context",
            "--before-edit",
            "src/mylib/helper.py",
            "--format",
            "json",
            "--path",
            str(repo),
        ],
    )

    data = json.loads(result.output)
    assert [item["owner"]["id"] for item in data["results"]] == ["helper"]
    [review] = data["claim_reviews"]
    assert review["doc"]["path"] == "docs/components/core.md"
    assert review["evidence"] == ["src/mylib/helper.py"]


def test_a_review_on_divergence_claim_is_queued_and_asks_its_own_question(
    tmp_path: Path,
) -> None:
    """The default relation is queued too, but addressed differently.

    A contract asks whether the code still obeys it. A claim where neither side wins
    asks which of the two is now wrong — the question a reader actually has to settle.
    """
    repo = _make_context_repo(tmp_path)

    result = runner.invoke(
        app,
        [
            "context",
            "--before-edit",
            "src/mylib/core.py",
            "--format",
            "json",
            "--path",
            str(repo),
        ],
    )

    data = json.loads(result.output)
    assert data["results"][0]["owner"]["id"] == "core"
    [review] = data["claim_reviews"]
    assert review["claim_id"] == "core-contract-1"
    assert review["relation"] == "review-on-divergence"
    assert "Neither one wins by default" in review["question"]
    assert "the code is what is wrong" not in review["question"]


def test_a_follows_evidence_claim_is_not_queued(tmp_path: Path) -> None:
    """The code wins, so changing it settles the question instead of raising one."""
    repo = _make_context_repo(tmp_path)
    doc = repo / "docs" / "components" / "core.md"
    doc.write_text(
        doc.read_text(encoding="utf-8").replace(
            "    kind: invariant\n",
            "    kind: invariant\n    relation: follows-evidence\n",
        ),
        encoding="utf-8",
    )

    result = runner.invoke(
        app,
        [
            "context",
            "--before-edit",
            "src/mylib/core.py",
            "--format",
            "json",
            "--path",
            str(repo),
        ],
    )

    data = json.loads(result.output)
    assert data["claim_reviews"] == []


def test_a_queued_claim_is_not_also_excerpted_as_content(tmp_path: Path) -> None:
    """One claim, one prompt. The review block says strictly more than the excerpt."""
    repo = _make_context_repo(tmp_path)
    _link_core(repo)
    _make_governing_claim(repo)

    result = runner.invoke(
        app,
        [
            "context",
            "--before-edit",
            "src/mylib/core.py",
            "--format",
            "json",
            "--path",
            str(repo),
        ],
    )

    data = json.loads(result.output)
    [review] = data["claim_reviews"]
    assert review["claim_id"] == "core-contract-1"
    categories = [item["category"] for item in data["results"][0]["content"]["included"]]
    assert "claims" not in categories

    plain = runner.invoke(
        app, ["context", "--before-edit", "src/mylib/core.py", "--path", str(repo)]
    )
    assert plain.output.count("Core invariant 1 remains true.") == 1


def _rfc(index: int) -> str:
    return (
        f"---\nid: {index:04d}-widget-change\ntitle: Widget change {index}\n"
        f"status: stable\nrfc_state: draft\naffects:\n  - core\n"
        f"summary: Change {index} to the widget.\n---\n\n"
        f"# Widget change {index}\n\nA proposal.\n"
    )


def test_active_rfcs_are_bounded_and_say_how_many_were_left_out(tmp_path: Path) -> None:
    """The RFC list is the one part of the packet that grows with the repository rather
    than with the change. At 1000 RFCs on one component it was 98.8% of the output, an
    unranked list plus a generated action each, with nothing saying so."""
    repo = _make_context_repo(tmp_path)
    (repo / "docs" / "rfcs").mkdir(parents=True, exist_ok=True)
    for index in range(1, 26):
        (repo / "docs" / "rfcs" / f"{index:04d}-widget-change.md").write_text(
            _rfc(index), encoding="utf-8"
        )

    result = runner.invoke(
        app,
        ["context", "--before-edit", "src/mylib/core.py", "--format", "json", "--path", str(repo)],
    )
    data = json.loads(result.output)
    changes = data["results"][0]["active_changes"]

    assert len(changes["shown"]) == 8
    assert changes["omitted"] == 17
    assert changes["retrieve"] == "irminsul change status <rfc-id>"
    # One action per shown RFC, not one per RFC in the repository.
    assert sum(a["command"].startswith("irminsul change status") for a in data["next_actions"]) == 8


def test_a_short_rfc_list_is_reported_as_complete(tmp_path: Path) -> None:
    """A reader must be able to tell a complete list from a selection, which is why the
    count is always present rather than inferred from the list's length."""
    repo = _make_context_repo(tmp_path)
    _add_active_rfc(repo)

    result = runner.invoke(
        app,
        ["context", "--before-edit", "src/mylib/core.py", "--format", "json", "--path", str(repo)],
    )
    changes = json.loads(result.output)["results"][0]["active_changes"]

    assert changes["omitted"] == 0
    assert changes["omitted_ids"] == []
    assert changes["retrieve"] is None


def test_the_plain_packet_names_the_omission_and_how_to_retrieve_it(tmp_path: Path) -> None:
    repo = _make_context_repo(tmp_path)
    (repo / "docs" / "rfcs").mkdir(parents=True, exist_ok=True)
    for index in range(1, 26):
        (repo / "docs" / "rfcs" / f"{index:04d}-widget-change.md").write_text(
            _rfc(index), encoding="utf-8"
        )

    result = runner.invoke(
        app, ["context", "--before-edit", "src/mylib/core.py", "--path", str(repo)]
    )

    assert "... and 17 more: " in result.output
    assert "see `irminsul change status <rfc-id>`" in result.output


def test_every_omitted_rfc_is_named_and_the_named_command_shows_it(tmp_path: Path) -> None:
    """The bound used to spend an id and hand back a count plus `irminsul list lifecycle`.
    That command lists lifecycle findings and the accepted backlog, and every RFC eligible
    here is `draft` or `accepted` — so an omitted draft appeared in neither, and the packet
    named a command that did not show the rest. Each id is now named, and the command the
    packet points at resolves each one."""
    repo = _make_context_repo(tmp_path)
    (repo / "docs" / "rfcs").mkdir(parents=True, exist_ok=True)
    for index in range(1, 26):
        (repo / "docs" / "rfcs" / f"{index:04d}-widget-change.md").write_text(
            _rfc(index), encoding="utf-8"
        )

    changes = json.loads(
        runner.invoke(
            app,
            [
                "context",
                "--before-edit",
                "src/mylib/core.py",
                "--format",
                "json",
                "--path",
                str(repo),
            ],
        ).output
    )["results"][0]["active_changes"]
    shown = {change["id"] for change in changes["shown"]}
    omitted = changes["omitted_ids"]

    assert len(omitted) == changes["omitted"]
    assert not shown & set(omitted)
    assert shown | set(omitted) == {f"{index:04d}-widget-change" for index in range(1, 26)}

    # The pointer is a command, so it has to run. The old one did not name these at all.
    for rfc_id in omitted[:3]:
        status = runner.invoke(app, ["change", "status", rfc_id, "--path", str(repo)])
        assert status.exit_code == 0 and rfc_id in status.output

    lifecycle = runner.invoke(app, ["list", "lifecycle", "--path", str(repo)])
    assert not any(rfc_id in lifecycle.output for rfc_id in omitted)
