"""Tests for `irminsul init --topology siblings`.

The siblings layout is a docs repo and a code repo side by side under one
parent directory. The scaffolder runs inside the docs repo and has to produce
an `irminsul.toml` whose `source_roots` reach out through `../`, plus CI that
rebuilds that shape from two checkouts.
"""

from __future__ import annotations

from pathlib import Path

import pytest
import typer
from ruamel.yaml import YAML
from typer.testing import CliRunner, Result

from irminsul.cli import app
from irminsul.init.command import _posix_join, ci_code_checkout_path, parse_code_repo

runner = CliRunner()
_yaml = YAML(typ="safe")


def _symlink(link: Path, target: Path) -> None:
    try:
        link.symlink_to(target, target_is_directory=True)
    except OSError as exc:  # pragma: no cover - Windows without developer mode
        pytest.skip(f"symlink creation unavailable: {exc}")


def _docs_repo(tmp_path: Path) -> Path:
    """An empty docs repo inside a workspace that can hold a sibling."""
    repo = tmp_path / "workspace" / "docs"
    repo.mkdir(parents=True)
    return repo


def _init_siblings(repo: Path, code_repo: str, *extra: str) -> Result:
    return runner.invoke(
        app,
        [
            "init",
            "--topology",
            "siblings",
            "--code-repo",
            code_repo,
            "--no-interactive",
            "--path",
            str(repo),
            *extra,
        ],
    )


# ---------------------------------------------------------------------------
# parse_code_repo unit tests
# ---------------------------------------------------------------------------


def test_parse_github_spec_becomes_a_sibling_dir(tmp_path: Path) -> None:
    docs = _docs_repo(tmp_path)
    spec, code_dir = parse_code_repo("acme/my-public-code", docs_root=docs)
    assert spec == "acme/my-public-code"
    assert code_dir == "../my-public-code"


def test_parse_relative_sibling_path(tmp_path: Path) -> None:
    docs = _docs_repo(tmp_path)
    spec, code_dir = parse_code_repo("../code", docs_root=docs)
    assert spec is None
    assert code_dir == "../code"


def test_parse_bare_name_is_read_as_a_sibling(tmp_path: Path) -> None:
    docs = _docs_repo(tmp_path)
    spec, code_dir = parse_code_repo("code", docs_root=docs)
    assert spec is None
    assert code_dir == "../code"


def test_parse_bare_name_matching_a_nested_directory_is_rejected(tmp_path: Path) -> None:
    """`--code-repo code` with `./code/` already inside the docs repo is
    ambiguous, and the nested reading is the one the deleted layout used. The
    rejection written for exactly that mistake has to be what the user sees,
    rather than a silent reinterpretation into `../code`."""
    docs = _docs_repo(tmp_path)
    (docs / "code").mkdir()

    with pytest.raises(typer.BadParameter, match="sibling"):
        parse_code_repo("code", docs_root=docs)


def test_parse_reads_the_coordinate_out_of_a_github_url(tmp_path: Path) -> None:
    """The owner and the repo are right there in the URL, and without them the
    generated workflow ships an `OWNER/CODE-REPO` placeholder the user has to
    fill in by hand."""
    docs = _docs_repo(tmp_path)
    assert parse_code_repo("https://github.com/acme/repo", docs_root=docs) == (
        "acme/repo",
        "../repo",
    )
    assert parse_code_repo("https://github.com/acme/repo.git", docs_root=docs) == (
        "acme/repo",
        "../repo",
    )


def test_parse_reads_the_coordinate_out_of_a_git_ssh_url(tmp_path: Path) -> None:
    """`git@github.com:acme/repo.git` was accepted as the coordinate itself,
    which `actions/checkout` cannot use, and named the checkout directory
    `repo.git` — a clone produces `repo/`."""
    docs = _docs_repo(tmp_path)
    assert parse_code_repo("git@github.com:acme/repo.git", docs_root=docs) == (
        "acme/repo",
        "../repo",
    )


def test_parse_keeps_a_non_github_url_local(tmp_path: Path) -> None:
    """CI can only generate a checkout step for a GitHub coordinate, so any
    other host stays a local path with the placeholder note."""
    docs = _docs_repo(tmp_path)
    spec, code_dir = parse_code_repo("https://gitlab.com/acme/repo", docs_root=docs)
    assert spec is None
    assert code_dir == "../repo"


def test_parse_normalises_windows_separators(tmp_path: Path) -> None:
    """`..\\code` is what a Windows shell hands over. Unnormalized it read as a
    bare name and wrote `../..\\code/src` into `paths.source_roots`, plus a CI
    `path:` containing `..`, which `actions/checkout` rejects."""
    docs = _docs_repo(tmp_path)
    assert parse_code_repo("..\\code", docs_root=docs) == (None, "../code")


def test_parse_expands_a_tilde_path(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """`~` was already read as "this is a path" but never expanded, so a
    legitimate sibling resolved under the docs repo and was refused."""
    docs = _docs_repo(tmp_path)
    monkeypatch.setenv("HOME", str(docs.parent))
    monkeypatch.setenv("USERPROFILE", str(docs.parent))

    assert parse_code_repo("~/code", docs_root=docs) == (None, "../code")


def test_parse_does_not_resolve_through_a_symlinked_sibling(tmp_path: Path) -> None:
    """The user named `../code`; resolving through the link renamed the sibling
    to its target in `paths.source_roots`, and rejected the value outright when
    the target lived outside the workspace."""
    docs = _docs_repo(tmp_path)
    target = docs.parent.parent / "elsewhere"
    target.mkdir()
    _symlink(docs.parent / "code", target)

    assert parse_code_repo("../code", docs_root=docs) == (None, "../code")


def test_parse_absolute_sibling_path(tmp_path: Path) -> None:
    docs = _docs_repo(tmp_path)
    code = docs.parent / "code"
    spec, code_dir = parse_code_repo(str(code), docs_root=docs)
    assert spec is None
    assert code_dir == "../code"


def test_parse_rejects_a_path_inside_the_docs_repo(tmp_path: Path) -> None:
    """The deleted nested layout: a code checkout inside the docs repo. It has
    to fail loudly rather than scaffold something the tool no longer supports."""
    docs = _docs_repo(tmp_path)
    with pytest.raises(typer.BadParameter, match="sibling"):
        parse_code_repo("./code", docs_root=docs)


def test_parse_rejects_a_path_outside_the_shared_parent(tmp_path: Path) -> None:
    docs = _docs_repo(tmp_path)
    with pytest.raises(typer.BadParameter, match="sibling"):
        parse_code_repo("../../elsewhere/code", docs_root=docs)


def test_parse_rejects_the_docs_repo_itself(tmp_path: Path) -> None:
    """`--code-repo .` names the docs repo, which is a sibling of everything
    the docs repo is a sibling of. Without the identity clause it would be
    accepted and the docs repo configured as its own code repo."""
    docs = _docs_repo(tmp_path)
    with pytest.raises(typer.BadParameter, match="sibling"):
        parse_code_repo(".", docs_root=docs)


def test_detected_source_roots_are_normalised_onto_the_code_dir(tmp_path: Path) -> None:
    """A language profile may offer `.` as a source-root candidate — Go does,
    for a flat module — and an unnormalized join writes `../code/.` into
    `paths.source_roots`."""
    assert _posix_join("../code", "src") == "../code/src"
    assert _posix_join("../code", ".") == "../code"


def test_ci_code_checkout_path_mirrors_the_local_layout() -> None:
    """`source_roots` are resolved from the docs checkout, so CI has to place
    the code repo exactly where `code_dir` points relative to it."""
    assert ci_code_checkout_path("../my-code") == "workspace/my-code"


# ---------------------------------------------------------------------------
# CLI integration
# ---------------------------------------------------------------------------


def test_siblings_writes_source_roots_through_the_parent(tmp_path: Path) -> None:
    repo = _docs_repo(tmp_path)
    result = _init_siblings(repo, "acme/public-code")
    assert result.exit_code == 0, result.stdout

    toml = (repo / "irminsul.toml").read_text(encoding="utf-8")
    assert 'source_roots = ["../public-code/src"]' in toml
    assert "enabled = []" in toml


def test_siblings_detects_languages_from_an_existing_code_repo(tmp_path: Path) -> None:
    repo = _docs_repo(tmp_path)
    code = repo.parent / "public-code"
    (code / "src").mkdir(parents=True)
    (code / "pyproject.toml").write_text("[project]\nname='x'\n", encoding="utf-8")

    result = _init_siblings(repo, "acme/public-code")
    assert result.exit_code == 0, result.stdout

    toml = (repo / "irminsul.toml").read_text(encoding="utf-8")
    assert 'source_roots = ["../public-code/src"]' in toml
    assert 'enabled = ["python"]' in toml


def test_siblings_does_not_gitignore_anything(tmp_path: Path) -> None:
    """The code repo lives outside the docs repo, so there is nothing for the
    docs repo's .gitignore to hide."""
    repo = _docs_repo(tmp_path)
    result = _init_siblings(repo, "acme/public-code")
    assert result.exit_code == 0, result.stdout
    assert not (repo / ".gitignore").exists()


def test_siblings_creates_agent_manifests(tmp_path: Path) -> None:
    repo = _docs_repo(tmp_path)
    result = _init_siblings(repo, "acme/public-code")
    assert result.exit_code == 0, result.stdout

    docs_manifest = (repo / "docs" / "AGENTS.md").read_text(encoding="utf-8")
    assert "<!-- agents-manifest:generated-start -->" in docs_manifest
    assert (repo / "AGENTS.md").is_file()


def test_siblings_workflow_checks_out_both_repos_under_one_parent(tmp_path: Path) -> None:
    repo = _docs_repo(tmp_path)
    result = _init_siblings(repo, "acme/public-code")
    assert result.exit_code == 0, result.stdout

    workflow = _yaml.load(
        (repo / ".github" / "workflows" / "docs-pr.yml").read_text(encoding="utf-8")
    )
    steps = workflow["jobs"]["check"]["steps"]
    checkouts = [s for s in steps if str(s.get("uses", "")).startswith("actions/checkout")]
    assert [s["with"]["path"] for s in checkouts] == ["workspace/docs", "workspace/public-code"]
    assert checkouts[1]["with"]["repository"] == "acme/public-code"

    run_step = steps[-1]
    assert run_step["run"] == "irminsul check --profile=hard"
    assert run_step["working-directory"] == "workspace/docs"


def test_siblings_nightly_workflow_runs_the_configured_profile(tmp_path: Path) -> None:
    repo = _docs_repo(tmp_path)
    result = _init_siblings(repo, "acme/public-code")
    assert result.exit_code == 0, result.stdout

    workflow = _yaml.load(
        (repo / ".github" / "workflows" / "docs-nightly.yml").read_text(encoding="utf-8")
    )
    run_step = workflow["jobs"]["audit"]["steps"][-1]
    assert run_step["run"] == "irminsul check --profile=configured"
    assert run_step["working-directory"] == "workspace/docs"


def test_siblings_local_path_leaves_the_checkout_to_be_filled_in(tmp_path: Path) -> None:
    """Without a GitHub coordinate the workflow cannot name the code repo, so
    it ships a placeholder and says so instead of emitting a broken step."""
    repo = _docs_repo(tmp_path)
    result = _init_siblings(repo, "../local-code")
    assert result.exit_code == 0, result.stdout

    pr_workflow = (repo / ".github" / "workflows" / "docs-pr.yml").read_text(encoding="utf-8")
    assert "repository: OWNER/CODE-REPO" in pr_workflow
    assert "path: workspace/local-code" in pr_workflow
    assert "Fill in `repository:`" in pr_workflow
    assert "fill in the `repository:`" in result.stdout


def test_siblings_scaffold_passes_the_hard_check(tmp_path: Path) -> None:
    repo = _docs_repo(tmp_path)
    result = _init_siblings(repo, "acme/public-code")
    assert result.exit_code == 0, result.stdout

    check_result = runner.invoke(app, ["check", "--profile", "hard", "--path", str(repo)])
    assert check_result.exit_code == 0, check_result.stdout


def test_siblings_requires_code_repo_when_non_interactive(tmp_path: Path) -> None:
    repo = _docs_repo(tmp_path)
    result = runner.invoke(
        app,
        ["init", "--topology", "siblings", "--no-interactive", "--path", str(repo)],
    )
    assert result.exit_code != 0
    assert not (repo / "irminsul.toml").exists()


def test_siblings_refuses_a_directory_that_holds_code(tmp_path: Path) -> None:
    repo = _docs_repo(tmp_path)
    (repo / "pyproject.toml").write_text("[project]\nname='x'\n", encoding="utf-8")

    result = _init_siblings(repo, "acme/public-code")
    assert result.exit_code == 2
    assert "irminsul init" in result.stdout
    assert not (repo / "irminsul.toml").exists()


def test_siblings_rejects_fresh(tmp_path: Path) -> None:
    """`--fresh` answers a question the siblings layout does not ask: whether
    the code repo exists is read off the disk."""
    repo = _docs_repo(tmp_path)
    result = _init_siblings(repo, "acme/public-code", "--fresh")
    assert result.exit_code == 2
    assert "--topology siblings" in result.stdout
    assert not (repo / "irminsul.toml").exists()


def test_code_repo_requires_the_siblings_topology(tmp_path: Path) -> None:
    """`--code-repo` is meaningless outside the siblings layout, so it has to be
    refused rather than ignored.

    The target deliberately holds code signals: without them `init
    --no-interactive` refuses for an unrelated reason, and the refusal happens
    to exit 2 and to mention `--topology siblings`, so a test pointed at an
    empty directory passes whether or not the guard exists. Here the run would
    otherwise scaffold a same-repo layout successfully and silently drop
    `--code-repo`, which is exactly the outcome the guard prevents. The
    assertion is on the guard's own sentence for the same reason.
    """
    target = tmp_path / "demo"
    (target / "src").mkdir(parents=True)
    (target / "pyproject.toml").write_text("[project]\nname='demo'\n", encoding="utf-8")

    result = runner.invoke(
        app,
        [
            "init",
            "--code-repo",
            "acme/ignored",
            "--no-interactive",
            "--path",
            str(target),
        ],
    )
    assert result.exit_code == 2, result.stdout
    assert "`--code-repo` is only valid with `--topology siblings`." in result.stdout
    assert not (target / "irminsul.toml").exists()


def test_init_errors_when_no_code_signals_noninteractive(tmp_path: Path) -> None:
    repo = _docs_repo(tmp_path)
    result = runner.invoke(app, ["init", "--no-interactive", "--path", str(repo)])
    assert result.exit_code == 2
    assert "irminsul init --fresh" in result.stdout
    assert "irminsul init --topology siblings --code-repo <spec-or-path>" in result.stdout


def test_init_interactive_no_code_can_choose_siblings(tmp_path: Path) -> None:
    repo = _docs_repo(tmp_path)
    # "2" chooses siblings, then the code repo spec, then the project name
    # default, then "n" declines the post-scaffold seed prompt.
    result = runner.invoke(app, ["init", "--path", str(repo)], input="2\nacme/public-code\n\nn\n")

    assert result.exit_code == 0, result.stdout
    assert "siblings" in result.stdout
    toml = (repo / "irminsul.toml").read_text(encoding="utf-8")
    assert 'source_roots = ["../public-code/src"]' in toml


def test_siblings_offers_the_seed_prompt(tmp_path: Path) -> None:
    """The siblings layout is only reachable in a directory with no code in it,
    so it scaffolds a brand-new project just as `--fresh` does. The prompt was
    dropped along with the retired `--fresh --topology docs-only` path that
    used to carry it."""
    repo = _docs_repo(tmp_path)

    result = runner.invoke(
        app,
        ["init", "--topology", "siblings", "--code-repo", "acme/public-code", "--path", str(repo)],
        input="\nn\n",
    )

    assert result.exit_code == 0, result.stdout
    assert "principle, idea, and belief" in result.stdout
    assert "irminsul seed" in result.stdout


def test_non_interactive_siblings_stays_scriptable(tmp_path: Path) -> None:
    """The mirror: `--no-interactive` gains no prompt."""
    repo = _docs_repo(tmp_path)

    result = _init_siblings(repo, "acme/public-code")

    assert result.exit_code == 0, result.stdout
    assert "principle, idea, and belief" not in result.stdout
