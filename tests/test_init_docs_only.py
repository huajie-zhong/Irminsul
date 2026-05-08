"""Tests for `irminsul init-docs-only`."""

from __future__ import annotations

from pathlib import Path

from typer.testing import CliRunner

from irminsul.cli import app
from irminsul.init.command import parse_code_repo, update_gitignore

runner = CliRunner()


# ---------------------------------------------------------------------------
# parse_code_repo unit tests
# ---------------------------------------------------------------------------


def test_parse_github_spec() -> None:
    spec, subfolder = parse_code_repo("acme/my-public-code")
    assert spec == "acme/my-public-code"
    assert subfolder == "my-public-code"


def test_parse_local_relative_path() -> None:
    spec, subfolder = parse_code_repo("./local-code")
    assert spec is None
    assert subfolder == "local-code"


def test_parse_local_dotdot_path() -> None:
    spec, subfolder = parse_code_repo("../sibling")
    assert spec is None
    assert subfolder == "sibling"


def test_parse_url() -> None:
    spec, subfolder = parse_code_repo("https://github.com/acme/repo")
    assert spec is None
    assert subfolder == "repo"


# ---------------------------------------------------------------------------
# update_gitignore unit tests
# ---------------------------------------------------------------------------


def test_update_gitignore_creates_file(tmp_path: Path) -> None:
    update_gitignore(tmp_path, "my-code")
    content = (tmp_path / ".gitignore").read_text(encoding="utf-8")
    assert "/my-code/" in content
    assert "Irminsul" in content


def test_update_gitignore_idempotent(tmp_path: Path) -> None:
    update_gitignore(tmp_path, "my-code")
    update_gitignore(tmp_path, "my-code")
    content = (tmp_path / ".gitignore").read_text(encoding="utf-8")
    assert content.count("/my-code/") == 1


def test_update_gitignore_appends_to_existing(tmp_path: Path) -> None:
    (tmp_path / ".gitignore").write_text("*.pyc\n__pycache__/\n", encoding="utf-8")
    update_gitignore(tmp_path, "ext-code")
    content = (tmp_path / ".gitignore").read_text(encoding="utf-8")
    assert "*.pyc" in content
    assert "/ext-code/" in content


# ---------------------------------------------------------------------------
# CLI integration tests
# ---------------------------------------------------------------------------


def _make_empty_dir(tmp_path: Path) -> Path:
    repo = tmp_path / "docs-repo"
    repo.mkdir()
    return repo


def test_init_docs_only_github_spec(tmp_path: Path) -> None:
    repo = _make_empty_dir(tmp_path)
    result = runner.invoke(
        app,
        [
            "init-docs-only",
            "--code-repo",
            "acme/public-code",
            "--no-interactive",
            "--path",
            str(repo),
        ],
    )
    assert result.exit_code == 0, result.output
    assert (repo / "irminsul.toml").exists()
    assert (repo / ".gitignore").exists()
    gi = (repo / ".gitignore").read_text(encoding="utf-8")
    assert "/public-code/" in gi


def test_init_docs_only_source_roots_in_toml(tmp_path: Path) -> None:
    repo = _make_empty_dir(tmp_path)
    runner.invoke(
        app,
        [
            "init-docs-only",
            "--code-repo",
            "acme/myrepo",
            "--no-interactive",
            "--path",
            str(repo),
        ],
    )
    toml = (repo / "irminsul.toml").read_text(encoding="utf-8")
    assert "myrepo" in toml


def test_init_docs_only_with_preexisting_subfolder(tmp_path: Path) -> None:
    repo = _make_empty_dir(tmp_path)
    # Pre-create subfolder with Python signals
    code = repo / "mycode"
    code.mkdir()
    (code / "pyproject.toml").write_text("[project]\nname='x'\n", encoding="utf-8")
    (code / "src").mkdir()

    runner.invoke(
        app,
        [
            "init-docs-only",
            "--code-repo",
            "./mycode",
            "--no-interactive",
            "--path",
            str(repo),
        ],
    )
    toml = (repo / "irminsul.toml").read_text(encoding="utf-8")
    assert "mycode" in toml


def test_init_docs_only_workflow_has_dual_checkout(tmp_path: Path) -> None:
    repo = _make_empty_dir(tmp_path)
    runner.invoke(
        app,
        [
            "init-docs-only",
            "--code-repo",
            "acme/public-code",
            "--no-interactive",
            "--path",
            str(repo),
        ],
    )
    pr_workflow = (repo / ".github" / "workflows" / "docs-pr.yml").read_text(encoding="utf-8")
    assert "repository: acme/public-code" in pr_workflow
    assert "path: public-code" in pr_workflow


def test_init_docs_only_local_path_no_checkout_step(tmp_path: Path) -> None:
    repo = _make_empty_dir(tmp_path)
    runner.invoke(
        app,
        [
            "init-docs-only",
            "--code-repo",
            "./local-code",
            "--no-interactive",
            "--path",
            str(repo),
        ],
    )
    pr_workflow = (repo / ".github" / "workflows" / "docs-pr.yml").read_text(encoding="utf-8")
    assert "repository:" not in pr_workflow


def test_init_docs_only_no_code_repo_noninteractive_errors(tmp_path: Path) -> None:
    repo = _make_empty_dir(tmp_path)
    result = runner.invoke(
        app,
        ["init-docs-only", "--no-interactive", "--path", str(repo)],
    )
    assert result.exit_code != 0


def test_init_errors_when_no_code_signals_noninteractive(tmp_path: Path) -> None:
    repo = _make_empty_dir(tmp_path)
    result = runner.invoke(app, ["init", "--no-interactive", "--path", str(repo)])
    assert result.exit_code == 2


def test_init_docs_only_warns_when_code_signals_present_noninteractive(tmp_path: Path) -> None:
    repo = _make_empty_dir(tmp_path)
    (repo / "pyproject.toml").write_text("[project]\nname='x'\n", encoding="utf-8")
    result = runner.invoke(
        app,
        [
            "init-docs-only",
            "--code-repo",
            "acme/x",
            "--no-interactive",
            "--path",
            str(repo),
        ],
    )
    assert result.exit_code == 2
