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


def test_init_then_check_passes_on_freshly_scaffolded_repo(tmp_path: Path) -> None:
    """The scaffold should produce a repo that passes irminsul check on its own."""
    target = tmp_path / "demo"
    target.mkdir()
    # Give it a minimal source root so globs/uniqueness don't trip on missing dirs.
    (target / "src").mkdir()
    (target / "src" / "demo.py").write_text("def x(): pass\n")

    result = runner.invoke(app, ["init", "--no-interactive", "--path", str(target)])
    assert result.exit_code == 0

    check_result = runner.invoke(app, ["check", "--scope", "hard", "--path", str(target)])
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
