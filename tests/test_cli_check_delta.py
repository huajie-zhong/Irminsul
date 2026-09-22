"""End-to-end tests for `irminsul check --delta`."""

from __future__ import annotations

import json
import subprocess
from collections.abc import Callable
from pathlib import Path

from typer.testing import CliRunner

from irminsul.cli import app

from .conftest import open_repo, seed_repo

runner = CliRunner()


def _init_repo(root: Path) -> str:
    return seed_repo(root)


def _check(repo: Path, *args: str) -> tuple[int, str]:
    result = runner.invoke(app, ["check", "--path", str(repo), *args])
    return result.exit_code, result.output


def test_delta_reports_only_the_new_finding(fixture_repo: Callable[[str], Path]) -> None:
    repo = fixture_repo("good")
    _init_repo(repo)

    old_doc = repo / "docs" / "components" / "legacy.md"
    old_doc.write_text("# Legacy without frontmatter\n", encoding="utf-8")
    with open_repo(repo) as handle:
        handle.git.add("-A")
        handle.index.commit("legacy doc")

    code, out = _check(repo)
    assert code == 1
    assert "legacy.md" in out

    new_doc = repo / "docs" / "components" / "new-bad.md"
    new_doc.write_text("# No frontmatter here\n", encoding="utf-8")

    code, out = _check(repo, "--delta")
    assert code == 1
    assert "[frontmatter/missing-frontmatter]" in out
    assert "new-bad.md" in out
    assert "legacy.md" not in out
    assert "1 new finding(s) vs HEAD (1 pre-existing suppressed)" in out


def test_delta_refuses_an_unchanged_tree(fixture_repo: Callable[[str], Path]) -> None:
    """Against an unchanged tree every finding is pre-existing, so the run suppressed
    all of them and exited 0 while checking nothing — a green run for any tree."""
    repo = fixture_repo("good")
    _init_repo(repo)

    code, out = _check(repo, "--delta")
    assert code == 2
    assert "identical to HEAD" in out


def test_delta_refuses_a_base_rev_naming_the_working_tree(
    fixture_repo: Callable[[str], Path],
) -> None:
    """The refusal was keyed to `--delta-base` being absent, and its own message
    suggested passing one — so the vacuous run was a single spelling away."""
    repo = fixture_repo("good")
    _init_repo(repo)

    for spelling in (
        "HEAD",
        subprocess.run(
            ["git", "-C", str(repo), "rev-parse", "HEAD"],
            capture_output=True,
            text=True,
            check=True,
        ).stdout.strip(),
    ):
        code, out = _check(repo, "--delta-base", spelling)
        assert code == 2, f"--delta-base {spelling} was not refused"
        assert "nothing to compare" in out


def test_delta_refusal_survives_an_untracked_scratch_file(
    fixture_repo: Callable[[str], Path],
) -> None:
    """The refusal asked whether the tree was dirty, and an untracked file counts —
    so one scratch file beside the repository bought a green run that suppressed every
    finding in it."""
    repo = fixture_repo("good")
    _init_repo(repo)
    (repo / "zzz.tmp").write_text("scratch\n", encoding="utf-8")

    code, out = _check(repo, "--delta")
    assert code == 2
    assert "nothing to compare" in out


def test_delta_runs_when_a_watched_file_is_untracked(
    fixture_repo: Callable[[str], Path],
) -> None:
    """A new doc is untracked too, and it is exactly what --delta exists to judge."""
    repo = fixture_repo("good")
    _init_repo(repo)
    (repo / "docs" / "components" / "new-bad.md").write_text(
        "# No frontmatter here\n", encoding="utf-8"
    )

    code, out = _check(repo, "--delta")
    assert code == 1
    assert "new-bad.md" in out


def test_delta_suppresses_pre_existing_findings_beside_an_edit(
    fixture_repo: Callable[[str], Path],
) -> None:
    repo = fixture_repo("good")
    _init_repo(repo)
    (repo / "docs" / "components" / "INDEX.md").write_text(
        (repo / "docs" / "components" / "INDEX.md").read_text(encoding="utf-8") + "\nMore.\n",
        encoding="utf-8",
    )

    code, out = _check(repo, "--delta")
    assert code == 0
    assert "new finding(s) vs HEAD" in out


def test_delta_exit_code_reflects_only_new_errors(fixture_repo: Callable[[str], Path]) -> None:
    repo = fixture_repo("good")
    _init_repo(repo)

    extra_doc = repo / "docs" / "components" / "extra.md"
    extra_doc.write_text(
        "---\n"
        "id: extra\n"
        "title: Extra Component\n"
        ""
        "status: stable\n"
        "describes: []\n"
        "---\n\n"
        "# Extra\n\n"
        "The extra component is planned for later.\n\n"
        "## Scope & Limitations\n\n"
        "Does not do anything beyond existing for this test.\n",
        encoding="utf-8",
    )
    index = repo / "docs" / "components" / "INDEX.md"
    index.write_text(index.read_text(encoding="utf-8") + "- [Extra](extra.md)\n", encoding="utf-8")

    code, out = _check(repo, "--delta")
    assert code == 0  # the new finding is a hint, which does not block
    assert "[reality/speculative-language]" in out

    code, _ = _check(repo, "--delta", "--strict")
    assert code == 1  # --strict promotes the new warning


def test_delta_base_flag_implies_delta(fixture_repo: Callable[[str], Path]) -> None:
    repo = fixture_repo("good")
    _init_repo(repo)

    new_doc = repo / "docs" / "components" / "new-bad.md"
    new_doc.write_text("# No frontmatter here\n", encoding="utf-8")

    code, out = _check(repo, "--delta-base", "HEAD")
    assert code == 1
    assert "new finding(s) vs HEAD" in out


def test_delta_json_format_reports_only_delta_findings(
    fixture_repo: Callable[[str], Path],
) -> None:
    repo = fixture_repo("good")
    _init_repo(repo)

    new_doc = repo / "docs" / "components" / "new-bad.md"
    new_doc.write_text("# No frontmatter here\n", encoding="utf-8")

    code, out = _check(repo, "--delta", "--format", "json")
    assert code == 1
    data = json.loads(out)
    assert data["delta"] == {
        "applied": True,
        "base": "HEAD",
        "new": 1,
        "pre_existing_suppressed": 0,
    }
    paths = {f["path"] for f in data["findings"]}
    assert paths == {"docs/components/new-bad.md"}
    assert data["baseline"]["applied"] is False


def test_delta_github_format_annotates_only_new_finding(
    fixture_repo: Callable[[str], Path],
) -> None:
    repo = fixture_repo("good")
    _init_repo(repo)

    new_doc = repo / "docs" / "components" / "new-bad.md"
    new_doc.write_text("# No frontmatter here\n", encoding="utf-8")

    code, out = _check(repo, "--delta", "--format", "github")
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
    _init_repo(root)


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
    components = repo / "docs" / "components"
    components.mkdir(parents=True)
    (components / "INDEX.md").write_text("# Components\n", encoding="utf-8")
    (repo / "irminsul.toml").write_text(
        'project_name = "siblings"\n[paths]\ndocs_root = "docs"\nsource_roots = ["../code/src"]\n',
        encoding="utf-8",
    )
    _seed_repo(repo)

    code, out = _check(repo, "--delta")
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
    components = repo / "docs" / "components"
    components.mkdir(parents=True)
    (components / "INDEX.md").write_text("# Components\n", encoding="utf-8")
    (repo / "irminsul.toml").write_text(
        'project_name = "siblings"\n[paths]\ndocs_root = "docs"\nsource_roots = ["../code/src"]\n',
        encoding="utf-8",
    )
    _seed_repo(repo)

    code, out = _check(repo)
    assert code != 2
    assert "siblings layout" not in out


def test_delta_cleans_up_scratch_worktree(fixture_repo: Callable[[str], Path]) -> None:
    repo = fixture_repo("good")
    _init_repo(repo)

    new_doc = repo / "docs" / "components" / "new-bad.md"
    new_doc.write_text("# No frontmatter here\n", encoding="utf-8")

    _check(repo, "--delta")

    with open_repo(repo) as git_repo:
        porcelain = git_repo.git.worktree("list", "--porcelain")
    assert porcelain.count("worktree ") == 1
