"""Tests for `irminsul context`."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

from typer.testing import CliRunner

import irminsul.context as context_module
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
    (docs / "a-core-note.md").write_text(
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


def test_git_changed_paths_parses_nul_porcelain_special_paths(tmp_path: Path, monkeypatch) -> None:
    class Result:
        returncode = 0
        stdout = " M src/tab\tfile.py\0?? src/back\\slash.py\0R  src/new name.py\0src/old name.py\0"
        stderr = ""

    def fake_run(args, **kwargs):
        assert "-z" in args
        return Result()

    monkeypatch.setattr(context_module.subprocess, "run", fake_run)

    assert context_module._git_changed_paths(tmp_path) == [
        "src/back\\slash.py",
        "src/new name.py",
        "src/tab\tfile.py",
    ]


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


def test_context_missing_path_is_nonzero(tmp_path: Path) -> None:
    repo = _make_context_repo(tmp_path)

    result = runner.invoke(app, ["context", "src/mylib/missing.py", "--path", str(repo)])

    assert result.exit_code == 1
    assert "path does not exist" in result.output


def test_context_no_topic_matches_is_nonzero(tmp_path: Path) -> None:
    repo = _make_context_repo(tmp_path)

    result = runner.invoke(app, ["context", "--topic", "absent", "--path", str(repo)])

    assert result.exit_code == 1
    assert "no docs matched topic" in result.output
