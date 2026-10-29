"""End-to-end tests for `irminsul check --delta`."""

from __future__ import annotations

import datetime as _dt
import json
import subprocess
from collections.abc import Callable
from pathlib import Path

import pytest
from typer.testing import CliRunner

from irminsul import docgraph

from .conftest import (
    commit_all,
    commit_file,
    git_init,
    invoke,
    open_repo,
    seed_repo,
    write,
    write_config,
    write_doc,
)

runner = CliRunner()


def test_delta_reports_only_the_new_finding(fixture_repo: Callable[[str], Path]) -> None:
    repo = fixture_repo("good")
    seed_repo(repo)

    old_doc = repo / "docs" / "components" / "legacy.md"
    old_doc.write_text("# Legacy without frontmatter\n", encoding="utf-8")
    with open_repo(repo) as handle:
        handle.git.add("-A")
        handle.index.commit("legacy doc")

    code, out = invoke(repo, "check")
    assert code == 1
    assert "legacy.md" in out

    new_doc = repo / "docs" / "components" / "new-bad.md"
    new_doc.write_text("# No frontmatter here\n", encoding="utf-8")

    code, out = invoke(repo, "check", "--delta")
    assert code == 1
    assert "[frontmatter/missing-frontmatter]" in out
    assert "new-bad.md" in out
    assert "legacy.md" not in out
    assert "1 new finding(s) vs HEAD (1 pre-existing suppressed)" in out


def test_delta_refuses_an_unchanged_tree(fixture_repo: Callable[[str], Path]) -> None:
    """Against an unchanged tree every finding is pre-existing, so the run suppressed
    all of them and exited 0 while checking nothing — a green run for any tree."""
    repo = fixture_repo("good")
    seed_repo(repo)

    code, out = invoke(repo, "check", "--delta")
    assert code == 2
    assert "identical to HEAD" in out


def test_delta_refuses_a_base_rev_naming_the_working_tree(
    fixture_repo: Callable[[str], Path],
) -> None:
    """The refusal was keyed to `--delta-base` being absent, and its own message
    suggested passing one — so the vacuous run was a single spelling away."""
    repo = fixture_repo("good")
    seed_repo(repo)

    for spelling in (
        "HEAD",
        subprocess.run(
            ["git", "-C", str(repo), "rev-parse", "HEAD"],
            capture_output=True,
            text=True,
            check=True,
        ).stdout.strip(),
    ):
        code, out = invoke(repo, "check", "--delta-base", spelling)
        assert code == 2, f"--delta-base {spelling} was not refused"
        assert "nothing to compare" in out


def test_delta_refusal_survives_an_untracked_scratch_file(
    fixture_repo: Callable[[str], Path],
) -> None:
    """The refusal asked whether the tree was dirty, and an untracked file counts —
    so one scratch file beside the repository bought a green run that suppressed every
    finding in it."""
    repo = fixture_repo("good")
    seed_repo(repo)
    (repo / "zzz.tmp").write_text("scratch\n", encoding="utf-8")

    code, out = invoke(repo, "check", "--delta")
    assert code == 2
    assert "nothing to compare" in out


def test_delta_runs_when_a_watched_file_is_untracked(
    fixture_repo: Callable[[str], Path],
) -> None:
    """A new doc is untracked too, and it is exactly what --delta exists to judge."""
    repo = fixture_repo("good")
    seed_repo(repo)
    (repo / "docs" / "components" / "new-bad.md").write_text(
        "# No frontmatter here\n", encoding="utf-8"
    )

    code, out = invoke(repo, "check", "--delta")
    assert code == 1
    assert "new-bad.md" in out


def test_delta_suppresses_pre_existing_findings_beside_an_edit(
    fixture_repo: Callable[[str], Path],
) -> None:
    repo = fixture_repo("good")
    seed_repo(repo)
    (repo / "docs" / "components" / "INDEX.md").write_text(
        (repo / "docs" / "components" / "INDEX.md").read_text(encoding="utf-8") + "\nMore.\n",
        encoding="utf-8",
    )

    code, out = invoke(repo, "check", "--delta")
    assert code == 0
    assert "new finding(s) vs HEAD" in out


def test_delta_exit_code_reflects_only_new_errors(fixture_repo: Callable[[str], Path]) -> None:
    repo = fixture_repo("good")
    seed_repo(repo)

    extra_doc = repo / "docs" / "components" / "extra.md"
    extra_doc.write_text(
        "---\n"
        "id: extra\n"
        "title: Extra Component\n"
        ""
        "status: stable\nsummary: A test doc.\n"
        "describes: []\n"
        "---\n\n"
        "# Extra\n\n"
        "The extra component runs through `extra_run()`.\n\n"
        "## Scope & Limitations\n\n"
        "Does not do anything beyond existing for this test.\n",
        encoding="utf-8",
    )
    index = repo / "docs" / "components" / "INDEX.md"
    index.write_text(index.read_text(encoding="utf-8") + "- [Extra](extra.md)\n", encoding="utf-8")

    code, out = invoke(repo, "check", "--delta")
    assert code == 0  # the new finding is a hint, which does not block
    assert "[code-references/unknown-symbol]" in out

    code, _ = invoke(repo, "check", "--delta", "--fail-on", "hint")
    assert code == 1  # --fail-on hint promotes the new warning


def test_delta_base_flag_implies_delta(fixture_repo: Callable[[str], Path]) -> None:
    repo = fixture_repo("good")
    seed_repo(repo)

    new_doc = repo / "docs" / "components" / "new-bad.md"
    new_doc.write_text("# No frontmatter here\n", encoding="utf-8")

    code, out = invoke(repo, "check", "--delta-base", "HEAD")
    assert code == 1
    assert "new finding(s) vs HEAD" in out


def test_delta_json_format_reports_only_delta_findings(
    fixture_repo: Callable[[str], Path],
) -> None:
    repo = fixture_repo("good")
    seed_repo(repo)

    new_doc = repo / "docs" / "components" / "new-bad.md"
    new_doc.write_text("# No frontmatter here\n", encoding="utf-8")

    code, out = invoke(repo, "check", "--delta", "--format", "json")
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
    seed_repo(repo)

    new_doc = repo / "docs" / "components" / "new-bad.md"
    new_doc.write_text("# No frontmatter here\n", encoding="utf-8")

    code, out = invoke(repo, "check", "--delta", "--format", "github")
    assert code == 1
    assert "::error" in out
    assert "new-bad.md" in out
    assert "composer.md" not in out


def test_delta_conflicts_with_no_baseline(fixture_repo: Callable[[str], Path]) -> None:
    repo = fixture_repo("good")
    seed_repo(repo)

    for flags in (["--delta"], ["--delta-base", "HEAD"]):
        code, out = invoke(repo, "check", *flags, "--no-baseline")
        assert code == 2
        assert "mutually exclusive" in out


def test_delta_unresolvable_base_exits_loudly(fixture_repo: Callable[[str], Path]) -> None:
    repo = fixture_repo("good")
    seed_repo(repo)

    code, out = invoke(repo, "check", "--delta-base", "no-such-rev")
    assert code == 2
    assert "no-such-rev" in out


def test_delta_without_git_history_exits_loudly(fixture_repo: Callable[[str], Path]) -> None:
    repo = fixture_repo("good")
    # No git init: --delta has no base rev to check out against.

    code, out = invoke(repo, "check", "--delta")
    assert code == 2
    assert "git repository" in out


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
    seed_repo(workspace / "code")

    repo = workspace / "docs"
    components = repo / "docs" / "components"
    components.mkdir(parents=True)
    (components / "INDEX.md").write_text("# Components\n", encoding="utf-8")
    write_config(repo, project_name="siblings", source_roots=["../code/src"])
    seed_repo(repo)

    code, out = invoke(repo, "check", "--delta")
    assert code == 2
    assert "cannot compare across a repository boundary" in out
    assert "'../code/src'" in out


def test_delta_refuses_a_test_root_in_the_code_repository(tmp_path: Path) -> None:
    """A test root is a configured tree like a source root, and in the siblings layout it
    lives in the code repository too; the refusal names it as it names a source root."""
    workspace = tmp_path / "workspace"
    code_repo = workspace / "code"
    (code_repo / "src").mkdir(parents=True)
    (code_repo / "src" / "core.py").write_text("def f():\n    return 1\n", encoding="utf-8")
    (code_repo / "tests").mkdir()
    (code_repo / "tests" / "test_core.py").write_text("def test_f():\n    pass\n", encoding="utf-8")
    seed_repo(code_repo)

    repo = workspace / "docs"
    components = repo / "docs" / "components"
    components.mkdir(parents=True)
    (components / "INDEX.md").write_text("# Components\n", encoding="utf-8")
    write_config(
        repo,
        project_name="siblings",
        source_roots=["../code/src"],
        extra='test_roots = ["../code/tests"]\n',
    )
    seed_repo(repo)

    code, out = invoke(repo, "check", "--delta")
    assert code == 2
    assert "cannot compare across a repository boundary" in out
    assert "'../code/tests'" in out


def test_plain_check_still_works_in_the_siblings_layout(tmp_path: Path) -> None:
    """The guard is scoped to --delta: the message tells users to drop the flag,
    so plain `check` must keep working on the same tree."""
    workspace = tmp_path / "workspace"
    code_src = workspace / "code" / "src"
    code_src.mkdir(parents=True)
    (code_src / "core.py").write_text("def f():\n    return 1\n", encoding="utf-8")
    seed_repo(workspace / "code")

    repo = workspace / "docs"
    components = repo / "docs" / "components"
    components.mkdir(parents=True)
    (components / "INDEX.md").write_text("# Components\n", encoding="utf-8")
    write_config(repo, project_name="siblings", source_roots=["../code/src"])
    seed_repo(repo)

    code, out = invoke(repo, "check")
    assert code != 2
    assert "siblings layout" not in out


def test_delta_cleans_up_scratch_worktree(fixture_repo: Callable[[str], Path]) -> None:
    repo = fixture_repo("good")
    seed_repo(repo)

    new_doc = repo / "docs" / "components" / "new-bad.md"
    new_doc.write_text("# No frontmatter here\n", encoding="utf-8")

    invoke(repo, "check", "--delta")

    with open_repo(repo) as git_repo:
        porcelain = git_repo.git.worktree("list", "--porcelain")
    assert porcelain.count("worktree ") == 1


def test_a_mandatory_pass_finding_is_never_pre_existing(tmp_path: Path) -> None:
    """A corrupt adoption record is not debt: it says the exceptions the record grants
    cannot be trusted, and a baseline cannot hide it either. So it stays new under
    `--delta` even when the base held it, and the edit beside it does not make it go away."""
    root = tmp_path / "repo"
    (root / "docs" / "components").mkdir(parents=True)
    (root / "src").mkdir()
    write_config(
        root, project_name="d", source_roots=["src"], enabled=["frontmatter", "uniqueness"]
    )
    (root / "docs" / "components" / "core.md").write_text(
        "---\nid: core\ntitle: Core\nstatus: stable\nsummary: A test doc.\n"
        "describes:\n  - src/core.py\n---\n\n# Core\n\nThe core.\n",
        encoding="utf-8",
    )
    (root / "src" / "core.py").write_text("X = 1\n", encoding="utf-8")
    (root / ".irminsul-adoption.json").write_text(
        '{"version": 1, "unowned": 7}\n', encoding="utf-8"
    )
    seed_repo(root)
    assert "adoption-record/unreadable" in invoke(root, "check")[1]

    (root / "src" / "core.py").write_text("X = 2\n", encoding="utf-8")
    code, out = invoke(root, "check", "--delta")

    assert "adoption-record/unreadable" in out
    assert "1 new finding(s) vs HEAD (0 pre-existing suppressed)" in out
    assert code == 1


def test_an_ignore_comment_finding_is_never_pre_existing(
    fixture_repo: Callable[[str], Path],
) -> None:
    """An ignore comment that suppresses nothing cannot be baselined, because an obsolete
    exception is not debt to carry. A base revision that already held it does not make it
    debt either, so `--delta` reports it as new over an unrelated edit."""
    repo = fixture_repo("good")
    doc = repo / "docs" / "components" / "composer.md"
    doc.write_text(
        doc.read_text(encoding="utf-8")
        + '\n<!-- irminsul:ignore orphans reason="nothing to hide" -->\n',
        encoding="utf-8",
    )
    seed_repo(repo)
    index = repo / "docs" / "components" / "INDEX.md"
    index.write_text(index.read_text(encoding="utf-8") + "\nMore.\n", encoding="utf-8")

    code, out = invoke(repo, "check", "--delta")

    assert "[ignore-comment/unused]" in out
    assert code == 1


def _drifting_claims_repo(root: Path) -> None:
    """Two docs whose claims cite a workflow: `old.yml` changed in a commit after its doc,
    and `new.yml` changed after its doc only in the working tree."""
    at = _dt.datetime(2025, 1, 1, 12, tzinfo=_dt.UTC)
    write_config(root, source_roots=["src"], enabled=["claim-provenance"])
    git_init(root)
    commit_all(root, "config", when=at, paths=["irminsul.toml"])
    for name in ("old", "new"):
        commit_file(root, f".github/workflows/{name}.yml", "a: 1\n", "evidence", when=at)
        write_doc(
            root,
            f"docs/foundation/{name}.md",
            doc_id=name,
            body=f"Holds. <!-- claim:{name}-claim -->",
            frontmatter_extra=[
                "claims:",
                f"  - id: {name}-claim",
                "    state: enabled",
                "    kind: ci_gate",
                "    claim: The evidence exists.",
                "    evidence:",
                f"      - .github/workflows/{name}.yml",
            ],
        )
        commit_all(
            root, "doc", when=at + _dt.timedelta(minutes=1), paths=[f"docs/foundation/{name}.md"]
        )
    moved = at + _dt.timedelta(minutes=2)
    commit_file(root, ".github/workflows/old.yml", "a: 2\n", "evidence moves", when=moved)
    write(root, ".github/workflows/new.yml", "a: 3\n")


def test_delta_counts_uncommitted_drift_as_new_and_committed_drift_as_old(tmp_path: Path) -> None:
    _drifting_claims_repo(tmp_path)

    _, out = invoke(tmp_path, "check", "--delta")

    assert "claim 'new-claim' cites evidence changed after the doc" in out
    assert "old-claim" not in out
    assert "1 new finding(s) vs HEAD (1 pre-existing suppressed)" in out


def test_the_delta_base_pass_reads_commits_alone(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _drifting_claims_repo(tmp_path)
    built: list[object] = []
    real = docgraph.build_graph

    def spy(*args: object, **kwargs: object) -> docgraph.DocGraph:
        built.append(kwargs.get("committed_only"))
        return real(*args, **kwargs)  # type: ignore[arg-type]

    monkeypatch.setattr(docgraph, "build_graph", spy)

    invoke(tmp_path, "check", "--delta")

    assert built == [True]
