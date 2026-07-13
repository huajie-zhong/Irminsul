"""End-to-end tests for `irminsul check --diff <base>` co-change enforcement.

Each test builds a real tmp git repo: a doc claims source files via
`describes`, commits land, and the CLI is asked whether the diff against a
base ref shipped the owning docs alongside their claimed code.
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

from typer.testing import CliRunner

from irminsul.cli import app

runner = CliRunner()

_GIT = ["git", "-c", "user.name=t", "-c", "user.email=t@t", "-c", "commit.gpgsign=false"]


def _git(repo_root: Path, *args: str) -> str:
    proc = subprocess.run(
        [*_GIT, *args],
        cwd=repo_root,
        check=True,
        capture_output=True,
        text=True,
    )
    return proc.stdout.strip()


_DOC_BODY = (
    "---\n"
    "id: alpha\n"
    "title: Alpha\n"
    "audience: explanation\n"
    "tier: 3\n"
    "status: stable\n"
    "describes:\n"
    "  - app/alpha.py\n"
    "  - app/beta.py\n"
    "---\n"
    "\n"
    "# Alpha\n"
)

_TOML = (
    'project_name = "cochange"\n'
    "[paths]\n"
    'docs_root = "docs"\n'
    'source_roots = ["app"]\n'
    "[checks]\n"
    "hard = []\n"
    "soft_deterministic = []\n"
)


def _seed_repo(tmp_path: Path) -> tuple[Path, str]:
    """Create a committed repo; return (root, base sha) for diffing against."""
    repo_root = tmp_path / "repo"
    (repo_root / "app").mkdir(parents=True)
    (repo_root / "app" / "alpha.py").write_text("a = 1\n", encoding="utf-8")
    (repo_root / "app" / "beta.py").write_text("b = 1\n", encoding="utf-8")
    (repo_root / "app" / "unclaimed.py").write_text("u = 1\n", encoding="utf-8")
    docs = repo_root / "docs" / "20-components"
    docs.mkdir(parents=True)
    (docs / "alpha.md").write_text(_DOC_BODY, encoding="utf-8")
    (repo_root / "irminsul.toml").write_text(_TOML, encoding="utf-8")
    _git(repo_root, "init")
    _git(repo_root, "add", "-A")
    _git(repo_root, "commit", "-m", "seed")
    return repo_root, _git(repo_root, "rev-parse", "HEAD")


def _commit(repo_root: Path, message: str) -> None:
    _git(repo_root, "add", "-A")
    _git(repo_root, "commit", "-m", message)


def test_cochange_fires_when_claimed_source_changes_without_doc(tmp_path: Path) -> None:
    repo_root, base = _seed_repo(tmp_path)
    (repo_root / "app" / "alpha.py").write_text("a = 2\n", encoding="utf-8")
    _commit(repo_root, "change source only")

    result = runner.invoke(app, ["check", "--diff", base, "--path", str(repo_root)])
    assert result.exit_code == 0  # warning, not error
    assert "[co-change]" in result.stdout
    assert "docs/20-components/alpha.md" in result.stdout
    assert "app/alpha.py" in result.stdout
    assert "0 errors, 1 warning" in result.stdout


def test_cochange_silent_when_doc_changed_too(tmp_path: Path) -> None:
    repo_root, base = _seed_repo(tmp_path)
    (repo_root / "app" / "alpha.py").write_text("a = 2\n", encoding="utf-8")
    doc = repo_root / "docs" / "20-components" / "alpha.md"
    doc.write_text(_DOC_BODY + "\nNow `a` is 2.\n", encoding="utf-8")
    _commit(repo_root, "change source and doc together")

    result = runner.invoke(app, ["check", "--diff", base, "--path", str(repo_root)])
    assert result.exit_code == 0
    assert "co-change" not in result.stdout
    assert "0 errors, 0 warnings" in result.stdout


def test_cochange_silent_for_unclaimed_files(tmp_path: Path) -> None:
    repo_root, base = _seed_repo(tmp_path)
    (repo_root / "app" / "unclaimed.py").write_text("u = 2\n", encoding="utf-8")
    _commit(repo_root, "change unclaimed file")

    result = runner.invoke(app, ["check", "--diff", base, "--path", str(repo_root)])
    assert result.exit_code == 0
    assert "co-change" not in result.stdout
    assert "0 errors, 0 warnings" in result.stdout


def test_cochange_groups_files_into_one_finding_per_doc(tmp_path: Path) -> None:
    repo_root, base = _seed_repo(tmp_path)
    (repo_root / "app" / "alpha.py").write_text("a = 2\n", encoding="utf-8")
    (repo_root / "app" / "beta.py").write_text("b = 2\n", encoding="utf-8")
    _commit(repo_root, "change both claimed sources")

    result = runner.invoke(app, ["check", "--diff", base, "--path", str(repo_root)])
    assert result.exit_code == 0
    assert result.stdout.count("[co-change]") == 1
    assert "app/alpha.py, app/beta.py" in result.stdout
    assert "0 errors, 1 warning" in result.stdout


def test_cochange_invalid_base_ref_exits_2(tmp_path: Path) -> None:
    repo_root, _base = _seed_repo(tmp_path)

    result = runner.invoke(app, ["check", "--diff", "not-a-ref", "--path", str(repo_root)])
    assert result.exit_code == 2
    assert "not-a-ref" in result.stdout


def test_cochange_empty_diff_ref_exits_2(tmp_path: Path) -> None:
    """`--diff ""` must not silently disable the gate.

    A workflow templating `--diff ${{ github.base_ref }}` interpolates to the
    empty string on a `push` event; git resolves `...HEAD` as `HEAD...HEAD` and
    reports no changed files, so the gate would pass vacuously.
    """
    repo_root, _base = _seed_repo(tmp_path)
    (repo_root / "app" / "alpha.py").write_text("a = 2\n", encoding="utf-8")
    _commit(repo_root, "change source only")

    for blank in ("", "   "):
        result = runner.invoke(app, ["check", "--diff", blank, "--path", str(repo_root)])
        assert result.exit_code == 2
        assert "--diff" in result.output
        assert "empty value" in result.output


def test_cochange_no_git_repository_message_distinguishes_from_bad_ref(tmp_path: Path) -> None:
    repo_root, _base = _seed_repo(tmp_path)
    # An irminsul root that is not itself a git root: refs are fine, git is not.
    nested = repo_root / "nested"
    (nested / "docs").mkdir(parents=True)
    (nested / "irminsul.toml").write_text(_TOML, encoding="utf-8")

    result = runner.invoke(app, ["check", "--diff", "HEAD", "--path", str(nested)])
    assert result.exit_code == 2
    assert "no git repository with commit history found" in result.output
    assert "could not be resolved" not in result.output


def test_cochange_strict_promotes_to_exit_1(tmp_path: Path) -> None:
    repo_root, base = _seed_repo(tmp_path)
    (repo_root / "app" / "alpha.py").write_text("a = 2\n", encoding="utf-8")
    _commit(repo_root, "change source only")

    result = runner.invoke(app, ["check", "--diff", base, "--strict", "--path", str(repo_root)])
    assert result.exit_code == 1
    assert "[co-change]" in result.stdout


def test_cochange_findings_in_json_output(tmp_path: Path) -> None:
    repo_root, base = _seed_repo(tmp_path)
    (repo_root / "app" / "alpha.py").write_text("a = 2\n", encoding="utf-8")
    _commit(repo_root, "change source only")

    result = runner.invoke(
        app, ["check", "--diff", base, "--format", "json", "--path", str(repo_root)]
    )
    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    cochange = [f for f in payload["findings"] if f["check"] == "co-change"]
    assert len(cochange) == 1
    assert cochange[0]["severity"] == "warning"
    assert cochange[0]["path"] == "docs/20-components/alpha.md"
    assert cochange[0]["doc_id"] == "alpha"
    assert "app/alpha.py" in cochange[0]["message"]
    assert payload["summary"]["warnings"] == 1


def test_cochange_with_github_format(tmp_path: Path) -> None:
    repo_root, base = _seed_repo(tmp_path)
    (repo_root / "app" / "alpha.py").write_text("a = 2\n", encoding="utf-8")
    _commit(repo_root, "change source only")

    result = runner.invoke(
        app, ["check", "--diff", base, "--format", "github", "--path", str(repo_root)]
    )
    assert result.exit_code == 0
    lines = result.stdout.splitlines()
    annotations = [line for line in lines if line.startswith("::")]
    assert len(annotations) == 1
    assert annotations[0].startswith(
        "::warning file=docs/20-components/alpha.md,title=irminsul co-change::"
    )
    assert "app/alpha.py" in annotations[0]
    assert "0 errors, 1 warning" in lines[-1]


def test_diff_and_base_ref_are_mutually_exclusive(tmp_path: Path) -> None:
    repo_root, base = _seed_repo(tmp_path)
    result = runner.invoke(
        app,
        [
            "check",
            "--diff",
            base,
            "--base-ref",
            base,
            "--head-ref",
            "HEAD",
            "--path",
            str(repo_root),
        ],
    )
    assert result.exit_code == 2
    assert "mutually exclusive" in result.output


def test_cochange_fires_for_deleted_claimed_file(tmp_path: Path) -> None:
    repo_root, base = _seed_repo(tmp_path)
    (repo_root / "app" / "alpha.py").unlink()
    _commit(repo_root, "delete claimed source")
    result = runner.invoke(
        app, ["check", "--diff", base, "--format", "json", "--path", str(repo_root)]
    )
    data = json.loads(result.output)
    cochange = [f for f in data["findings"] if f["check"] == "co-change"]
    assert len(cochange) == 1
    assert "app/alpha.py" in cochange[0]["message"]
