"""Tests for cross-repo git mtime support — the siblings layout."""

from __future__ import annotations

from pathlib import Path

from irminsul.git.mtime import GitTime, git_root_for, last_commit_time_any_repo


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
    (docs_root / "docs" / "20-components" / "app.md").write_text(
        "---\n"
        "id: app\n"
        "title: App\n"
        "audience: explanation\n"
        "tier: 3\n"
        "status: stable\n"
        "describes:\n"
        "  - app.py\n"
        "---\n\n# App\n"
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


def _monorepo(tmp_path: Path) -> tuple[Path, Path]:
    """A git repo whose irminsul root is a subfolder, not the repo root.

    Returns (invocation_root, tracked_file). The only `.git` sits above the
    invocation root, so `git_root_for` has to walk *up* to reach it.
    """
    from git import Repo

    mono = tmp_path / "mono"
    proj = mono / "packages" / "proj"
    (proj / "docs").mkdir(parents=True)
    (proj / "docs" / "d.md").write_text("# d\n", encoding="utf-8")

    repo = Repo.init(mono)
    with repo.config_writer() as cw:
        cw.set_value("user", "name", "Test")
        cw.set_value("user", "email", "test@example.com")
        cw.set_value("commit", "gpgsign", "false")
    repo.git.add(A=True)
    repo.index.commit("monorepo")
    expected = repo.head.commit.hexsha
    repo.close()
    return proj, expected


def test_enclosing_repo_above_the_invocation_root_supplies_git_times(
    tmp_path: Path,
) -> None:
    """The invocation root is not always a repository root. In a monorepo
    subfolder the enclosing `.git` is an *ancestor* of it, and that ancestor is
    the only repo holding any history for the path.

    Pinned directly rather than left to incidental coverage: this repo's own
    fixture repos reach the same branch only because they happen to sit inside
    this git repo, which reads like an accident and invites deletion.
    """
    proj, expected_sha = _monorepo(tmp_path)
    doc = proj / "docs" / "d.md"

    result = last_commit_time_any_repo(doc, proj)

    assert result is not None
    assert result.sha == expected_sha
    assert result.when is not None


def test_repository_below_the_invocation_root_wins_over_the_enclosing_one(
    tmp_path: Path,
) -> None:
    """The other direction the nearest-`.git` rule covers, and the one the
    docstring names explicitly: a submodule or vendored checkout carrying its
    own `.git` *below* the invocation root. The enclosing repository still has
    history for the path — it tracked those files before they moved — so
    resolving against the invocation root would hand back the wrong commit
    rather than none, which is the failure mode that hides.
    """
    from git import Repo

    outer_root = tmp_path / "project"
    vendored = outer_root / "vendor" / "lib"
    vendored.mkdir(parents=True)
    tracked = vendored / "core.py"
    tracked.write_text("x = 1\n", encoding="utf-8")

    outer = Repo.init(outer_root)
    with outer.config_writer() as cw:
        cw.set_value("user", "name", "Test")
        cw.set_value("user", "email", "test@example.com")
        cw.set_value("commit", "gpgsign", "false")
    outer.git.add(A=True)
    outer.index.commit("vendored code was once ours")
    outer_sha = outer.head.commit.hexsha
    outer.git.rm("-r", "--cached", "vendor/lib")
    outer.index.commit("hand it to its own repository")
    outer.close()

    inner = Repo.init(vendored)
    with inner.config_writer() as cw:
        cw.set_value("user", "name", "Test")
        cw.set_value("user", "email", "test@example.com")
        cw.set_value("commit", "gpgsign", "false")
    inner.git.add(A=True)
    inner.index.commit("its own history")
    inner_sha = inner.head.commit.hexsha
    inner.close()

    result = last_commit_time_any_repo(tracked, outer_root)

    assert result is not None
    assert result.sha == inner_sha
    assert result.sha != outer_sha


def test_asking_the_invocation_root_alone_would_lose_the_history(tmp_path: Path) -> None:
    """The mirror, and the reason the branch cannot be collapsed: resolving
    against the invocation root instead of the enclosing repo yields no history
    at all, so every git time would silently vanish."""
    from irminsul.git.mtime import _bulk_lookup

    proj, _ = _monorepo(tmp_path)
    doc = proj / "docs" / "d.md"

    assert _bulk_lookup(proj, doc) == GitTime(sha=None, when=None)
