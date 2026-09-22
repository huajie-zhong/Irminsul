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
from click import unstyle
from ruamel.yaml import YAML
from typer.testing import CliRunner, Result

from irminsul.cli import app
from irminsul.init.command import _posix_join, ci_code_checkout_path, parse_code_repo

from .conftest import cli_output

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


def _init_siblings(
    repo: Path,
    code_repo: str,
    *extra: str,
    languages: tuple[str, ...] = ("python",),
) -> Result:
    language_args = [item for language in languages for item in ("--language", language)]
    return runner.invoke(
        app,
        [
            "init",
            "--topology",
            "siblings",
            "--code-repo",
            code_repo,
            *language_args,
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


def test_parse_reads_the_coordinate_out_of_a_deep_github_url(tmp_path: Path) -> None:
    """A browser hands over `.../tree/main` or `.../blob/main/...` URLs. The
    coordinate is the first two path segments; falling through to the generic
    URL branch named the checkout directory after the *branch* and shipped the
    placeholder CI — a silently wrong scaffold from a URL that plainly says
    `acme/repo`."""
    docs = _docs_repo(tmp_path)
    assert parse_code_repo("https://github.com/acme/repo/tree/main", docs_root=docs) == (
        "acme/repo",
        "../repo",
    )
    assert parse_code_repo("https://github.com/acme/repo.git/tree/main", docs_root=docs) == (
        "acme/repo",
        "../repo",
    )


def test_parse_rejects_a_github_url_without_a_repository(tmp_path: Path) -> None:
    """A github.com URL must never degrade into the local-path branch — with no
    repository in it there is nothing to parse, so it fails loudly."""
    docs = _docs_repo(tmp_path)
    with pytest.raises(typer.BadParameter, match="not a repository"):
        parse_code_repo("https://github.com/acme", docs_root=docs)


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
    """A code checkout inside the docs repo is a nested layout, which is not
    supported, so it fails loudly rather than scaffolding one."""
    docs = _docs_repo(tmp_path)
    with pytest.raises(typer.BadParameter, match="sibling"):
        parse_code_repo("./code", docs_root=docs)


def test_parse_rejects_a_path_outside_the_shared_parent(tmp_path: Path) -> None:
    docs = _docs_repo(tmp_path)
    with pytest.raises(typer.BadParameter, match="sibling"):
        parse_code_repo("../../elsewhere/code", docs_root=docs)


@pytest.mark.parametrize("value", ["../..", "code/..", "acme/.."])
def test_parse_rejects_a_dot_dot_tail(tmp_path: Path, value: str) -> None:
    """The containment test resolved only the containing directory, so a
    candidate ending in `..` kept `..` as its name: `../..` passed as a sibling
    called `..`, writing `source_roots = ["../../src"]` and CI that checks the
    code out on top of the docs checkout."""
    docs = _docs_repo(tmp_path)
    with pytest.raises(typer.BadParameter, match="sibling"):
        parse_code_repo(value, docs_root=docs)


def test_parse_strips_a_trailing_slash(tmp_path: Path) -> None:
    """Shell completion leaves `acme/repo/`, which stopped matching the
    `owner/repo` shorthand and was refused as a path inside the docs repo."""
    docs = _docs_repo(tmp_path)
    assert parse_code_repo("acme/repo/", docs_root=docs) == ("acme/repo", "../repo")
    assert parse_code_repo("../code/", docs_root=docs) == (None, "../code")


def test_parse_rejects_the_docs_repo_itself(tmp_path: Path) -> None:
    """`--code-repo .` names the docs repo, which is a sibling of everything
    the docs repo is a sibling of. Without the identity clause it would be
    accepted and the docs repo configured as its own code repo."""
    docs = _docs_repo(tmp_path)
    with pytest.raises(typer.BadParameter, match="sibling"):
        parse_code_repo(".", docs_root=docs)


def test_parse_rejects_a_code_repo_named_docs(tmp_path: Path) -> None:
    """The generated workflows check the docs repo out at `workspace/docs`, so a
    code sibling of the same name lands on top of it — the second checkout wipes
    the first and the gate runs in a tree with no `irminsul.toml`. Case folds
    because GitHub's macOS and Windows runners are case-insensitive."""
    docs = tmp_path / "workspace" / "product-docs"
    docs.mkdir(parents=True)
    for value in ("acme/docs", "../docs", "https://github.com/acme/Docs"):
        with pytest.raises(typer.BadParameter, match="workspace/docs"):
            parse_code_repo(value, docs_root=docs)


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
    assert 'enabled = ["python"]' in toml


def test_siblings_requires_language_for_an_absent_repo_before_writes(tmp_path: Path) -> None:
    repo = _docs_repo(tmp_path)
    result = _init_siblings(repo, "acme/public-code", languages=())

    assert result.exit_code == 2
    assert "--language" in unstyle(result.output)
    assert not (repo / "irminsul.toml").exists()
    assert not (repo / "docs").exists()


def test_siblings_prompts_for_language_when_the_repo_is_absent(tmp_path: Path) -> None:
    repo = _docs_repo(tmp_path)
    result = runner.invoke(
        app,
        [
            "init",
            "--topology",
            "siblings",
            "--code-repo",
            "acme/public-code",
            "--path",
            str(repo),
        ],
        input="\npython, typescript\nn\n",
    )

    assert result.exit_code == 0, result.stdout
    toml = (repo / "irminsul.toml").read_text(encoding="utf-8")
    assert 'enabled = ["python", "typescript"]' in toml


def test_siblings_detects_languages_from_an_existing_code_repo(tmp_path: Path) -> None:
    repo = _docs_repo(tmp_path)
    code = repo.parent / "public-code"
    (code / "src").mkdir(parents=True)
    (code / "pyproject.toml").write_text("[project]\nname='x'\n", encoding="utf-8")

    result = _init_siblings(repo, "acme/public-code", languages=())
    assert result.exit_code == 0, result.stdout

    toml = (repo / "irminsul.toml").read_text(encoding="utf-8")
    assert 'source_roots = ["../public-code/src"]' in toml
    assert 'enabled = ["python"]' in toml


def test_siblings_requires_language_when_detection_finds_none(tmp_path: Path) -> None:
    repo = _docs_repo(tmp_path)
    code = repo.parent / "public-code"
    code.mkdir()
    (code / "go.mod").write_text("module example.com/demo\n", encoding="utf-8")

    result = _init_siblings(repo, "acme/public-code", languages=())

    assert result.exit_code == 2
    assert "No supported language could be detected" in result.output
    assert "--language" in unstyle(result.output)
    assert not (repo / "irminsul.toml").exists()


def test_siblings_accepts_explicit_language_for_unsupported_detection(tmp_path: Path) -> None:
    repo = _docs_repo(tmp_path)
    code = repo.parent / "public-code"
    code.mkdir()
    (code / "go.mod").write_text("module example.com/demo\n", encoding="utf-8")

    result = _init_siblings(repo, "acme/public-code", languages=("go",))

    assert result.exit_code == 0, result.stdout
    toml = (repo / "irminsul.toml").read_text(encoding="utf-8")
    assert 'source_roots = ["../public-code"]' in toml
    assert 'enabled = ["go"]' in toml


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
    assert run_step["run"] == 'irminsul check --diff "origin/$BASE_REF"'
    assert run_step["working-directory"] == "workspace/docs"


def test_siblings_nightly_workflow_runs_the_configured_profile(tmp_path: Path) -> None:
    repo = _docs_repo(tmp_path)
    result = _init_siblings(repo, "acme/public-code")
    assert result.exit_code == 0, result.stdout

    workflow = _yaml.load(
        (repo / ".github" / "workflows" / "docs-nightly.yml").read_text(encoding="utf-8")
    )
    run_step = workflow["jobs"]["audit"]["steps"][-1]
    assert run_step["run"] == "irminsul check --fail-on time"
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

    check_result = runner.invoke(app, ["check", "--path", str(repo)])
    assert check_result.exit_code == 0, check_result.stdout


def test_siblings_selected_language_activates_schema_leak(tmp_path: Path) -> None:
    repo = _docs_repo(tmp_path)
    result = _init_siblings(repo, "acme/public-code")
    assert result.exit_code == 0, result.stdout

    (repo / "docs" / "components" / "user.md").write_text(
        "---\nid: user\ntitle: User\nstatus: stable\ndescribes: []\n---\n\n# User\n\n"
        "class User(BaseModel):\n",
        encoding="utf-8",
    )

    check_result = runner.invoke(app, ["check", "--path", str(repo)])
    assert check_result.exit_code == 1, check_result.stdout
    assert "schema-leak" in check_result.stdout


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
    assert "irminsul init" in cli_output(result)
    assert not (repo / "irminsul.toml").exists()


def test_retired_init_docs_only_command_is_gone() -> None:
    """`init-docs-only` is retired. Its tombstone only bites while the
    command stays gone: `retired-references` stands a tombstone down when the
    CLI identity is live again, so restoring the command would also disarm
    the guard against guidance that teaches it, and nothing else in the suite
    pinned the removal."""
    result = runner.invoke(app, ["init-docs-only", "--help"])

    assert result.exit_code == 2
    assert "No such command" in unstyle(result.output)


def test_retired_docs_only_topology_is_rejected(tmp_path: Path) -> None:
    repo = _docs_repo(tmp_path)

    result = runner.invoke(
        app,
        ["init", "--topology", "docs-only", "--no-interactive", "--path", str(repo)],
    )

    assert result.exit_code == 2
    assert not (repo / "irminsul.toml").exists()


def test_siblings_rejects_fresh(tmp_path: Path) -> None:
    """`--fresh` answers a question the siblings layout does not ask: whether
    the code repo exists is read off the disk."""
    repo = _docs_repo(tmp_path)
    result = _init_siblings(repo, "acme/public-code", "--fresh")
    assert result.exit_code == 2
    assert "--topology siblings" in cli_output(result)
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
    assert result.exit_code == 2, cli_output(result)
    assert "`--code-repo` is only valid with `--topology siblings`." in cli_output(result)
    assert not (target / "irminsul.toml").exists()


def test_init_errors_when_no_code_signals_noninteractive(tmp_path: Path) -> None:
    repo = _docs_repo(tmp_path)
    result = runner.invoke(app, ["init", "--no-interactive", "--path", str(repo)])
    assert result.exit_code == 2
    assert "irminsul init --fresh" in cli_output(result)
    assert "irminsul init --topology siblings --code-repo <spec-or-path>" in cli_output(result)


def test_init_interactive_no_code_can_choose_siblings(tmp_path: Path) -> None:
    repo = _docs_repo(tmp_path)
    # Choose siblings, enter the code repo, keep the default project name,
    # select Python, and decline the post-scaffold seed prompt.
    result = runner.invoke(
        app,
        ["init", "--path", str(repo)],
        input="2\nacme/public-code\n\npython\nn\n",
    )

    assert result.exit_code == 0, result.stdout
    assert "siblings" in result.stdout
    toml = (repo / "irminsul.toml").read_text(encoding="utf-8")
    assert 'source_roots = ["../public-code/src"]' in toml


def test_siblings_offers_the_seed_prompt(tmp_path: Path) -> None:
    """The siblings layout is only reachable in a directory with no code in it,
    so it scaffolds a brand-new project just as `--fresh` does and offers the
    same seed prompt."""
    repo = _docs_repo(tmp_path)

    result = runner.invoke(
        app,
        [
            "init",
            "--topology",
            "siblings",
            "--code-repo",
            "acme/public-code",
            "--language",
            "python",
            "--path",
            str(repo),
        ],
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


def test_siblings_next_steps_name_the_code_repo_registration(tmp_path: Path) -> None:
    """The harness files land in the docs repo, where init runs. A session
    opened in the code repo has neither, so step 4 says how to register the
    server from there, pointed back at this repo."""
    repo = _docs_repo(tmp_path)
    result = _init_siblings(repo, "acme/app")
    assert result.exit_code == 0, result.output

    output = unstyle(result.output)
    assert ".mcp.json registers the MCP server for sessions opened here" in output
    assert "from ../app/ run `claude mcp add irminsul -- irminsul mcp --path ../docs`" in output
    assert (repo / ".mcp.json").is_file()
    assert not (repo.parent / "app" / ".mcp.json").exists()


def test_the_code_repository_gate_is_scaffolded_outside_workflows(tmp_path: Path) -> None:
    """A gate for the *other* repository, written here because init cannot commit there.

    It must not land in `.github/workflows/`. This repository's CI would run it — on docs
    pull requests, against a code checkout nothing is reviewing — which is a confusing
    green tick rather than the gate anybody wanted.
    """
    from irminsul.init.command import InitAnswers, Topology, write_scaffold

    root = tmp_path / "docs"
    write_scaffold(
        root,
        InitAnswers(
            project_name="demo",
            languages=["python"],
            source_roots=["../code/src", "../code/lib"],
            github_user="acme",
            today="2026-09-20",
            topology=Topology.siblings,
            code_repo_spec="acme/code",
            code_dir="../code",
        ),
    )

    assert not (root / ".github" / "workflows" / "code-pr.yml").exists()
    workflow = (root / ".github" / "for-code-repo" / "code-pr.yml").read_text(encoding="utf-8")
    # No `paths:` filter, on purpose. It would be frozen at scaffold time — init never
    # writes `paths.test_roots`, so a test tree configured later would never appear in it —
    # and nothing seals this file the way `diff-integrity` seals the docs repo workflows,
    # because it lives in the other repository. A filter that stopped matching would be
    # invisible; judging an unrelated pull request is the cheaper mistake.
    # Parsed, not grepped: the prose above the `on:` block explains why there is no filter
    # and says the words `paths:` while doing it.
    triggers = _yaml.load(workflow)["on"]
    assert "pull_request" in triggers
    assert triggers["pull_request"] is None or "paths" not in triggers["pull_request"]
    assert "../code" not in workflow
    # The two axes: an empty range here, this pull request's range there.
    assert "--diff HEAD --source-diff" in workflow
    # And the two things it cannot install for the adopter.
    assert "DOCS_REPO_TOKEN" in workflow
    assert "branch-protection" in workflow


def test_init_names_the_checks_an_administrator_has_to_require(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """The one boundary this tool cannot cross, said at the one moment somebody is reading.

    Every finding Irminsul produces is a report until an administrator requires the check,
    and the tool can neither do that nor see whether it was done. So init names the workflow
    and the job by the names GitHub will show — and the expectations here are read out of the
    generated files rather than written down twice, because an instruction naming a job the
    scaffold stopped creating is worse than no instruction at all.
    """
    from irminsul.init.command import InitAnswers, Topology, print_next_steps, write_scaffold

    root = tmp_path / "workspace" / "docs"
    (tmp_path / "workspace" / "code" / "src").mkdir(parents=True)
    root.mkdir(parents=True)
    answers = InitAnswers(
        project_name="demo",
        languages=["python"],
        source_roots=["../code/src"],
        github_user="acme",
        today="2026-09-20",
        topology=Topology.siblings,
        code_repo_spec="acme/code",
        code_dir="../code",
    )
    write_scaffold(root, answers)

    print_next_steps(answers, [])
    printed = capsys.readouterr().out

    docs_gate = _yaml.load(
        (root / ".github" / "workflows" / "docs-pr.yml").read_text(encoding="utf-8")
    )
    code_gate = _yaml.load(
        (root / ".github" / "for-code-repo" / "code-pr.yml").read_text(encoding="utf-8")
    )
    docs_job = next(iter(docs_gate["jobs"]))
    code_job = next(iter(code_gate["jobs"]))

    # The docs-side gate: the job GitHub lists as a status check, and the file holding it.
    assert f"`{docs_job}`" in printed
    assert ".github/workflows/docs-pr.yml" in printed
    assert "Irminsul cannot do this" in printed
    # The source-side gate: named by its workflow name, reporting-only until required in the
    # other repository, whose settings this one cannot reach.
    assert f"`{code_gate['name']}`" in printed
    assert f"`{code_job}` job" in printed
    assert "reports only" in printed


def test_the_same_repo_layout_scaffolds_no_code_repository_gate(tmp_path: Path) -> None:
    """There is no other repository to gate, so there is no file to copy anywhere."""
    from irminsul.init.command import InitAnswers, write_scaffold

    write_scaffold(
        tmp_path,
        InitAnswers(
            project_name="demo",
            languages=["python"],
            source_roots=["src"],
            github_user="acme",
            today="2026-09-20",
        ),
    )

    assert not (tmp_path / ".github" / "for-code-repo").exists()


def test_the_scaffolded_source_ref_is_remote_tracking(tmp_path: Path) -> None:
    """Production CI has to measure the boundary against the remote's branch, not a local one.

    A local branch in a checkout is whatever that checkout has: a developer can move it, and
    nothing about moving it is visible to anybody else. `origin/main` in a CI checkout is what
    the remote had when the job fetched. Both spellings are accepted — a fully qualified
    `refs/heads/...` is explicit, which is why the fixtures in
    `tests/test_adoption_siblings.py` can use one — so what keeps production honest is which
    one the scaffold writes, and that is what this asserts.

    The paired assumption is that the ref is actually there to resolve, which is why the code
    checkout fetches full history. Neither of these is a claim that the branch is protected:
    Irminsul checks that a pin is contained in the ref's history and nothing more.
    """
    import tomllib

    from irminsul.init.command import InitAnswers, Topology, write_scaffold

    root = tmp_path / "workspace" / "docs"
    (tmp_path / "workspace" / "code" / "src").mkdir(parents=True)
    root.mkdir(parents=True)
    write_scaffold(
        root,
        InitAnswers(
            project_name="demo",
            languages=["python"],
            source_roots=["../code/src"],
            github_user="acme",
            today="2026-09-21",
            topology=Topology.siblings,
            code_repo_spec="acme/code",
            code_dir="../code",
        ),
    )

    config = tomllib.loads((root / "irminsul.toml").read_text(encoding="utf-8"))
    declared = config["paths"]["sources"]

    assert len(declared) == 1
    assert declared[0]["path"] == "../code"
    assert declared[0]["name"] == "code"
    # Remote-tracking, so it cannot be a branch somebody moved in the checkout.
    assert declared[0]["ref"].startswith("origin/")
    assert not declared[0]["ref"].startswith("refs/heads/")

    # And the checkout it will be resolved in fetches enough history to have it.
    workflow = _yaml.load(
        (root / ".github" / "workflows" / "docs-pr.yml").read_text(encoding="utf-8")
    )
    checkouts = [
        step
        for step in workflow["jobs"]["check"]["steps"]
        if str(step.get("uses", "")).startswith("actions/checkout")
    ]
    code_checkout = [step for step in checkouts if "repository" in step.get("with", {})]
    assert code_checkout, "the siblings workflow checks the code repository out"
    assert code_checkout[0]["with"]["fetch-depth"] == 0
