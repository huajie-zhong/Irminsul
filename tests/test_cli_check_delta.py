"""End-to-end tests for `irminsul check --delta`."""

from __future__ import annotations

import json
from collections.abc import Callable
from pathlib import Path

from git import Repo
from typer.testing import CliRunner

from irminsul.cli import app

runner = CliRunner()


def _init_repo(root: Path) -> Repo:
    repo = Repo.init(root)
    with repo.config_writer() as cw:
        cw.set_value("user", "name", "Test")
        cw.set_value("user", "email", "test@example.com")
    repo.git.add("-A")
    repo.index.commit("seed")
    return repo


def _check(repo: Path, *args: str) -> tuple[int, str]:
    result = runner.invoke(app, ["check", "--path", str(repo), *args])
    return result.exit_code, result.output


def test_delta_reports_only_the_new_finding(fixture_repo: Callable[[str], Path]) -> None:
    repo = fixture_repo("good")
    _init_repo(repo)

    # Sanity: the fixture has one pre-existing warning before any edit.
    code, out = _check(repo, "--profile", "configured")
    assert code == 0
    assert "[orphans/orphan-doc]" in out

    new_doc = repo / "docs" / "20-components" / "new-bad.md"
    new_doc.write_text("# No frontmatter here\n", encoding="utf-8")

    code, out = _check(repo, "--profile", "configured", "--delta")
    assert code == 1
    assert "[frontmatter/missing-frontmatter]" in out
    assert "new-bad.md" in out
    assert "composer.md" not in out
    assert "1 new finding(s) vs HEAD (1 pre-existing suppressed)" in out


def test_delta_suppresses_pre_existing_findings_on_clean_diff(
    fixture_repo: Callable[[str], Path],
) -> None:
    repo = fixture_repo("good")
    _init_repo(repo)

    code, out = _check(repo, "--profile", "configured", "--delta")
    assert code == 0
    assert "0 new finding(s) vs HEAD (1 pre-existing suppressed)" in out


def test_delta_exit_code_reflects_only_new_errors(fixture_repo: Callable[[str], Path]) -> None:
    repo = fixture_repo("good")
    _init_repo(repo)

    extra_doc = repo / "docs" / "20-components" / "extra.md"
    extra_doc.write_text(
        "---\n"
        "id: extra\n"
        "title: Extra Component\n"
        "audience: explanation\n"
        "tier: 3\n"
        "status: stable\n"
        "describes: []\n"
        "---\n\n"
        "# Extra\n\n"
        "Another component with no inbound references.\n\n"
        "## Scope & Limitations\n\n"
        "Does not do anything beyond existing for this test.\n",
        encoding="utf-8",
    )

    code, out = _check(repo, "--profile", "configured", "--delta")
    assert code == 0  # new finding is a warning only
    assert "[orphans/orphan-doc]" in out

    code, _ = _check(repo, "--profile", "configured", "--delta", "--strict")
    assert code == 1  # --strict promotes the new warning


def test_delta_base_flag_implies_delta(fixture_repo: Callable[[str], Path]) -> None:
    repo = fixture_repo("good")
    _init_repo(repo)

    new_doc = repo / "docs" / "20-components" / "new-bad.md"
    new_doc.write_text("# No frontmatter here\n", encoding="utf-8")

    code, out = _check(repo, "--profile", "configured", "--delta-base", "HEAD")
    assert code == 1
    assert "new finding(s) vs HEAD" in out


def test_delta_json_format_reports_only_delta_findings(
    fixture_repo: Callable[[str], Path],
) -> None:
    repo = fixture_repo("good")
    _init_repo(repo)

    new_doc = repo / "docs" / "20-components" / "new-bad.md"
    new_doc.write_text("# No frontmatter here\n", encoding="utf-8")

    code, out = _check(repo, "--profile", "configured", "--delta", "--format", "json")
    assert code == 1
    data = json.loads(out)
    assert data["delta"] == {
        "applied": True,
        "base": "HEAD",
        "new": 1,
        "pre_existing_suppressed": 1,
    }
    paths = {f["path"] for f in data["findings"]}
    assert paths == {"docs/20-components/new-bad.md"}
    assert data["baseline"]["applied"] is False


def test_delta_github_format_annotates_only_new_finding(
    fixture_repo: Callable[[str], Path],
) -> None:
    repo = fixture_repo("good")
    _init_repo(repo)

    new_doc = repo / "docs" / "20-components" / "new-bad.md"
    new_doc.write_text("# No frontmatter here\n", encoding="utf-8")

    code, out = _check(repo, "--profile", "configured", "--delta", "--format", "github")
    assert code == 1
    assert "::error" in out
    assert "new-bad.md" in out
    assert "composer.md" not in out


def test_delta_conflicts_with_update_baseline(fixture_repo: Callable[[str], Path]) -> None:
    repo = fixture_repo("good")
    _init_repo(repo)

    code, out = _check(repo, "--delta", "--update-baseline")
    assert code == 2
    assert "mutually exclusive" in out


def test_delta_unresolvable_base_exits_loudly(fixture_repo: Callable[[str], Path]) -> None:
    repo = fixture_repo("good")
    _init_repo(repo)

    code, out = _check(repo, "--delta-base", "no-such-rev")
    assert code == 2
    assert "no-such-rev" in out


def test_delta_without_git_history_exits_loudly(fixture_repo: Callable[[str], Path]) -> None:
    repo = fixture_repo("good")
    # No git init: --delta has no base rev to check out against.

    code, out = _check(repo, "--delta")
    assert code == 2
    assert "git repository" in out


def _seed_repo(root: Path) -> None:
    """Init a repo and release its handles — see the note in `test_delta.py`."""
    _init_repo(root).close()


def test_delta_refuses_the_siblings_layout(tmp_path: Path) -> None:
    """The docs repo and the code repo are separate repositories, so a worktree
    checkout of the docs repo carries no source at all. Without the guard the
    base run finds nothing under the code tree and every source-dependent
    finding survives as new — a wrong answer with a nonzero exit and no
    warning."""
    workspace = tmp_path / "workspace"
    code_src = workspace / "code" / "src"
    code_src.mkdir(parents=True)
    (code_src / "core.py").write_text("def f():\n    return 1\n", encoding="utf-8")
    _seed_repo(workspace / "code")

    repo = workspace / "docs"
    components = repo / "docs" / "20-components"
    components.mkdir(parents=True)
    (components / "INDEX.md").write_text("# Components\n", encoding="utf-8")
    (repo / "irminsul.toml").write_text(
        'project_name = "siblings"\n[paths]\ndocs_root = "docs"\nsource_roots = ["../code/src"]\n',
        encoding="utf-8",
    )
    _seed_repo(repo)

    code, out = _check(repo, "--profile", "hard", "--delta")
    assert code == 2
    assert "cannot compare across a repository boundary" in out
    assert "'../code/src'" in out


def test_plain_check_still_works_in_the_siblings_layout(tmp_path: Path) -> None:
    """The guard is scoped to --delta: the message tells users to drop the flag,
    so plain `check` must keep working on the same tree."""
    workspace = tmp_path / "workspace"
    code_src = workspace / "code" / "src"
    code_src.mkdir(parents=True)
    (code_src / "core.py").write_text("def f():\n    return 1\n", encoding="utf-8")
    _seed_repo(workspace / "code")

    repo = workspace / "docs"
    components = repo / "docs" / "20-components"
    components.mkdir(parents=True)
    (components / "INDEX.md").write_text("# Components\n", encoding="utf-8")
    (repo / "irminsul.toml").write_text(
        'project_name = "siblings"\n[paths]\ndocs_root = "docs"\nsource_roots = ["../code/src"]\n',
        encoding="utf-8",
    )
    _seed_repo(repo)

    code, out = _check(repo, "--profile", "hard")
    assert code != 2
    assert "siblings layout" not in out


def test_delta_cleans_up_scratch_worktree(fixture_repo: Callable[[str], Path]) -> None:
    repo = fixture_repo("good")
    git_repo = _init_repo(repo)

    new_doc = repo / "docs" / "20-components" / "new-bad.md"
    new_doc.write_text("# No frontmatter here\n", encoding="utf-8")

    _check(repo, "--delta")

    porcelain = git_repo.git.worktree("list", "--porcelain")
    assert porcelain.count("worktree ") == 1
