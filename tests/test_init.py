"""End-to-end tests for `irminsul init`."""

from __future__ import annotations

from pathlib import Path

from typer.testing import CliRunner

from irminsul.cli import app

runner = CliRunner()


def test_init_no_interactive_creates_expected_tree(tmp_path: Path) -> None:
    target = tmp_path / "demo"
    target.mkdir()
    (target / "src").mkdir()  # code signal required by --no-interactive guard
    result = runner.invoke(app, ["init", "--no-interactive", "--path", str(target)])
    assert result.exit_code == 0, result.stdout

    expected = [
        "irminsul.toml",
        "docs/README.md",
        "docs/GLOSSARY.md",
        "docs/CONTRIBUTING.md",
        "docs/00-foundation/principles.md",
        "docs/10-architecture/overview.md",
        "docs/20-components/INDEX.md",
        "docs/30-workflows/INDEX.md",
        "docs/40-reference/INDEX.md",
        "docs/50-decisions/INDEX.md",
        "docs/50-decisions/0001-adopt-irminsul.md",
        "docs/60-operations/INDEX.md",
        "docs/70-knowledge/INDEX.md",
        "docs/80-evolution/INDEX.md",
        "docs/90-meta/INDEX.md",
        ".github/workflows/docs-pr.yml",
        ".github/workflows/docs-nightly.yml",
    ]
    for rel in expected:
        assert (target / rel).is_file(), f"missing scaffold output: {rel}"


def test_init_scaffold_config_includes_only_useful_default_knobs(tmp_path: Path) -> None:
    target = tmp_path / "demo"
    target.mkdir()
    (target / "src").mkdir()
    result = runner.invoke(app, ["init", "--no-interactive", "--path", str(target)])
    assert result.exit_code == 0, result.stdout

    toml = (target / "irminsul.toml").read_text(encoding="utf-8")
    assert "[checks.external_links]" in toml
    assert "enabled = false" in toml
    assert "[checks.parent_child]" in toml
    assert "[checks.stale_reaper]" in toml


def test_init_fresh_no_interactive_creates_source_root(tmp_path: Path) -> None:
    target = tmp_path / "demo"
    result = runner.invoke(app, ["init", "--fresh", "--no-interactive", "--path", str(target)])
    assert result.exit_code == 0, result.stdout

    assert (target / "src").is_dir()
    assert (target / "irminsul.toml").is_file()
    toml = (target / "irminsul.toml").read_text(encoding="utf-8")
    assert 'source_roots = ["src"]' in toml
    assert "enabled = []" in toml


def test_init_fresh_generated_repo_passes_hard_check(tmp_path: Path) -> None:
    target = tmp_path / "demo"
    result = runner.invoke(app, ["init", "--fresh", "--no-interactive", "--path", str(target)])
    assert result.exit_code == 0, result.stdout

    check_result = runner.invoke(app, ["check", "--profile", "hard", "--path", str(target)])
    assert check_result.exit_code == 0, check_result.stdout


def test_init_interactive_no_code_can_choose_fresh_start(tmp_path: Path) -> None:
    target = tmp_path / "demo"
    target.mkdir()

    # "1" choose fresh-start, project name + render target defaults, "n" declines
    # the post-init seed prompt.
    result = runner.invoke(app, ["init", "--path", str(target)], input="1\n\n\nn\n")

    assert result.exit_code == 0, result.stdout
    assert "Fresh-start, same repo" in result.stdout
    assert (target / "src").is_dir()
    assert "enabled = []" in (target / "irminsul.toml").read_text(encoding="utf-8")


def test_init_fresh_docs_only_future_repo(tmp_path: Path) -> None:
    target = tmp_path / "docs-repo"
    result = runner.invoke(
        app,
        [
            "init",
            "--fresh",
            "--topology",
            "docs-only",
            "--code-repo",
            "acme/future-public-repo",
            "--no-interactive",
            "--path",
            str(target),
        ],
    )
    assert result.exit_code == 0, result.stdout
    assert not (target / "future-public-repo").exists()

    toml = (target / "irminsul.toml").read_text(encoding="utf-8")
    assert 'source_roots = ["future-public-repo/src"]' in toml
    assert "enabled = []" in toml

    gitignore = (target / ".gitignore").read_text(encoding="utf-8")
    assert "/future-public-repo/" in gitignore

    check_result = runner.invoke(app, ["check", "--profile", "hard", "--path", str(target)])
    assert check_result.exit_code == 0, check_result.stdout


def test_init_fresh_code_repo_requires_docs_only_topology(tmp_path: Path) -> None:
    target = tmp_path / "demo"
    result = runner.invoke(
        app,
        [
            "init",
            "--fresh",
            "--code-repo",
            "acme/ignored",
            "--no-interactive",
            "--path",
            str(target),
        ],
    )

    assert result.exit_code == 2
    assert "--topology docs-only" in result.stdout
    assert not (target / "irminsul.toml").exists()


def test_init_fresh_docs_only_warns_on_unknown_render_target(tmp_path: Path) -> None:
    target = tmp_path / "docs-repo"
    result = runner.invoke(
        app,
        [
            "init",
            "--fresh",
            "--topology",
            "docs-only",
            "--code-repo",
            "acme/future-public-repo",
            "--path",
            str(target),
        ],
        # project name default, "wat" render target, "n" declines the seed prompt.
        input="\nwat\nn\n",
    )

    assert result.exit_code == 0, result.stdout
    assert "unknown render target 'wat', using 'mkdocs'" in result.stdout
    assert 'target = "mkdocs"' in (target / "irminsul.toml").read_text(encoding="utf-8")


def test_init_fresh_docs_only_detects_existing_subfolder(tmp_path: Path) -> None:
    target = tmp_path / "docs-repo"
    code = target / "public-code"
    code.mkdir(parents=True)
    (code / "pyproject.toml").write_text("[project]\nname='x'\n", encoding="utf-8")
    (code / "src").mkdir()

    result = runner.invoke(
        app,
        [
            "init",
            "--fresh",
            "--topology",
            "docs-only",
            "--code-repo",
            "./public-code",
            "--no-interactive",
            "--path",
            str(target),
        ],
    )
    assert result.exit_code == 0, result.stdout

    toml = (target / "irminsul.toml").read_text(encoding="utf-8")
    assert 'source_roots = ["public-code/src"]' in toml
    assert 'enabled = ["python"]' in toml


def test_init_fresh_in_non_empty_no_code_directory(tmp_path: Path) -> None:
    target = tmp_path / "demo"
    target.mkdir()
    (target / "README.md").write_text("# Demo\n", encoding="utf-8")
    (target / ".gitignore").write_text(".env\n", encoding="utf-8")

    result = runner.invoke(app, ["init", "--fresh", "--no-interactive", "--path", str(target)])

    assert result.exit_code == 0, result.stdout
    assert (target / "README.md").read_text(encoding="utf-8") == "# Demo\n"
    assert (target / "src").is_dir()


def test_init_fresh_errors_when_code_signals_exist_without_override(tmp_path: Path) -> None:
    target = tmp_path / "demo"
    target.mkdir()
    (target / "src").mkdir()

    result = runner.invoke(app, ["init", "--fresh", "--no-interactive", "--path", str(target)])

    assert result.exit_code == 2
    assert "--allow-existing-code" in result.stdout


def test_init_fresh_allows_existing_code_with_explicit_override(tmp_path: Path) -> None:
    target = tmp_path / "demo"
    target.mkdir()
    (target / "src").mkdir()
    (target / "src" / "demo.py").write_text("def x(): pass\n", encoding="utf-8")

    result = runner.invoke(
        app,
        [
            "init",
            "--fresh",
            "--allow-existing-code",
            "--no-interactive",
            "--path",
            str(target),
        ],
    )

    assert result.exit_code == 0, result.stdout
    assert "enabled = []" in (target / "irminsul.toml").read_text(encoding="utf-8")


def test_init_fresh_does_not_overwrite_without_force(tmp_path: Path) -> None:
    target = tmp_path / "demo"
    target.mkdir()
    docs_dir = target / "docs" / "00-foundation"
    docs_dir.mkdir(parents=True)
    custom = docs_dir / "principles.md"
    custom.write_text("# my custom principles\n", encoding="utf-8")

    result = runner.invoke(app, ["init", "--fresh", "--no-interactive", "--path", str(target)])

    assert result.exit_code == 0, result.stdout
    assert custom.read_text(encoding="utf-8") == "# my custom principles\n"


def test_init_then_check_passes_on_freshly_scaffolded_repo(tmp_path: Path) -> None:
    """The scaffold should produce a repo that passes irminsul check on its own."""
    target = tmp_path / "demo"
    target.mkdir()
    # Give it a minimal source root so globs/uniqueness don't trip on missing dirs.
    (target / "src").mkdir()
    (target / "src" / "demo.py").write_text("def x(): pass\n")

    result = runner.invoke(app, ["init", "--no-interactive", "--path", str(target)])
    assert result.exit_code == 0

    check_result = runner.invoke(app, ["check", "--profile", "hard", "--path", str(target)])
    # The freshly-scaffolded repo has no `describes` claims yet so nothing
    # should be flagged. (Source coverage is advisory, not hard.)
    assert check_result.exit_code == 0, check_result.stdout


def test_init_does_not_overwrite_without_force(tmp_path: Path) -> None:
    target = tmp_path / "demo"
    target.mkdir()
    (target / "src").mkdir()  # code signal

    # Pre-create a scaffold file with custom content.
    docs_dir = target / "docs" / "00-foundation"
    docs_dir.mkdir(parents=True)
    custom = docs_dir / "principles.md"
    custom.write_text("# my custom principles\n")

    result = runner.invoke(app, ["init", "--no-interactive", "--path", str(target)])
    assert result.exit_code == 0

    assert custom.read_text() == "# my custom principles\n"


def test_init_force_overwrites_existing_files(tmp_path: Path) -> None:
    target = tmp_path / "demo"
    target.mkdir()
    (target / "src").mkdir()  # code signal
    docs_dir = target / "docs" / "00-foundation"
    docs_dir.mkdir(parents=True)
    custom = docs_dir / "principles.md"
    custom.write_text("# my custom principles\n")

    result = runner.invoke(app, ["init", "--no-interactive", "--force", "--path", str(target)])
    assert result.exit_code == 0
    assert "my custom principles" not in custom.read_text()
