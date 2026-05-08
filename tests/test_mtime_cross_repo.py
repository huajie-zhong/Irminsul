"""Tests for cross-repo git mtime support (Topology B)."""

from __future__ import annotations

from pathlib import Path

from irminsul.git.mtime import git_root_for, last_commit_time_any_repo


def test_git_root_for_finds_project_git(tmp_path: Path) -> None:
    # Use the project's own git repo as the "found" case.
    project_root = Path(__file__).parent.parent
    result = git_root_for(project_root / "src" / "irminsul" / "cli.py")
    assert result is not None
    assert (result / ".git").exists()


def test_git_root_for_returns_none_when_no_git(tmp_path: Path) -> None:
    some_file = tmp_path / "code" / "app.py"
    some_file.parent.mkdir(parents=True)
    some_file.write_text("# code")

    result = git_root_for(some_file)
    assert result is None


def test_last_commit_time_any_repo_same_repo(tmp_path: Path) -> None:
    # A same-repo path just delegates to last_commit_time; should not return None.
    project_root = Path(__file__).parent.parent
    docs_root = project_root
    result = last_commit_time_any_repo(project_root / "src" / "irminsul" / "cli.py", docs_root)
    # Not None (same-repo path — may be _NO_TIME if no commits, but never None)
    assert result is not None


def test_last_commit_time_any_repo_cross_repo_no_git(tmp_path: Path) -> None:
    docs = tmp_path / "docs"
    docs.mkdir()
    code_file = tmp_path / "code" / "app.py"
    code_file.parent.mkdir(parents=True)
    code_file.write_text("# code")

    result = last_commit_time_any_repo(code_file, docs)
    assert result is None


def test_last_commit_time_any_repo_cross_repo_with_git(tmp_path: Path) -> None:
    # Cross-repo path that IS under a git repo (the project's git).
    project_root = Path(__file__).parent.parent
    docs = tmp_path / "docs"
    docs.mkdir()

    # Point to a file inside the project's git repo — that's "cross-repo" relative to tmp docs.
    cross_repo_file = project_root / "src" / "irminsul" / "cli.py"
    result = last_commit_time_any_repo(cross_repo_file, docs)
    # Should not be None — git root found
    assert result is not None


def test_mtime_drift_cross_repo_no_git_emits_error(tmp_path: Path) -> None:
    """MtimeDriftCheck emits an error finding for cross-repo source with no .git."""
    import datetime

    from irminsul.checks.base import Severity
    from irminsul.checks.mtime_drift import MtimeDriftCheck
    from irminsul.docgraph import build_graph

    # Build a docs repo structure
    docs_root = tmp_path / "docs-repo"
    (docs_root / "docs" / "20-components").mkdir(parents=True)

    # Create a source file in a sibling dir with no .git
    code_dir = tmp_path / "code-no-git" / "src"
    code_dir.mkdir(parents=True)
    (code_dir / "app.py").write_text("# code")

    # Write a valid doc that describes the cross-repo source
    today = datetime.date.today().isoformat()
    (docs_root / "docs" / "20-components" / "app.md").write_text(
        f"---\n"
        f"id: app\n"
        f"title: App\n"
        f"audience: explanation\n"
        f"tier: 3\n"
        f"status: stable\n"
        f'owner: "@test"\n'
        f"last_reviewed: {today}\n"
        f"describes:\n"
        f"  - app.py\n"
        f"---\n\n# App\n"
    )

    # Write irminsul.toml pointing at the sibling code dir
    rel_source = Path("../code-no-git/src").as_posix()
    (docs_root / "irminsul.toml").write_text(
        f'project_name = "test"\n[paths]\ndocs_root = "docs"\nsource_roots = ["{rel_source}"]\n'
    )

    from irminsul.config import find_config, load

    config = load(find_config(docs_root))
    # Inject soft_deterministic to enable mtime-drift
    config = config.model_copy(
        update={"checks": config.checks.model_copy(update={"soft_deterministic": ["mtime-drift"]})}
    )
    graph = build_graph(docs_root, config)

    findings = MtimeDriftCheck().run(graph)

    error_findings = [f for f in findings if f.severity == Severity.error]
    assert error_findings, f"expected error finding for cross-repo no-git; got {findings}"
    assert any("no git history" in f.message for f in error_findings)
