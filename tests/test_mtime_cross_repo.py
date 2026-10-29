"""Tests for cross-repo git mtime support — the siblings layout."""

from __future__ import annotations

import datetime as _dt
from pathlib import Path

import pytest

from irminsul.git.mtime import GitTime, git_root_for, last_commit_time_any_repo, pending_time
from irminsul.git.reader import GitReader

from .conftest import git, seed_repo


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


def test_git_root_for_walks_up_from_the_resolved_path(tmp_path: Path) -> None:
    """`docs/../code/app.py` lives in `code`, so the `.git` beside `docs` is not its root."""
    (tmp_path / "docs" / ".git").mkdir(parents=True)
    app = tmp_path / "code" / "app.py"
    app.parent.mkdir()
    app.write_text("# code")
    spelled = tmp_path / "docs" / ".." / "code" / "app.py"

    assert git_root_for(spelled) is None

    (tmp_path / "code" / ".git").mkdir()
    assert git_root_for(spelled) == (tmp_path / "code").resolve()


@pytest.mark.parametrize("layout", ["same-repo", "cross-repo"])
def test_last_commit_time_any_repo_finds_the_projects_git(tmp_path: Path, layout: str) -> None:
    """A same-repo path resolves through the docs repo's own git, a cross-repo path through the
    nearest `.git` above it (here, the project's own); neither is ever None."""
    project_root = Path(__file__).parent.parent
    docs_root = project_root
    if layout == "cross-repo":
        docs_root = tmp_path / "docs"
        docs_root.mkdir()

    result = last_commit_time_any_repo(
        GitReader(), project_root / "src" / "irminsul" / "cli.py", docs_root
    )

    assert result is not None


def test_last_commit_time_any_repo_cross_repo_no_git(tmp_path: Path) -> None:
    docs = tmp_path / "docs"
    docs.mkdir()
    code_file = tmp_path / "code" / "app.py"
    code_file.parent.mkdir(parents=True)
    code_file.write_text("# code")

    result = last_commit_time_any_repo(GitReader(), code_file, docs)
    assert result is None


def test_mtime_drift_cross_repo_no_git_emits_error(tmp_path: Path) -> None:
    """MtimeDriftCheck emits an error finding for cross-repo source with no .git."""
    from irminsul.checks.base import Severity
    from irminsul.checks.mtime_drift import MtimeDriftCheck
    from irminsul.docgraph import build_graph

    # Build a docs repo structure
    docs_root = tmp_path / "docs-repo"
    (docs_root / "docs" / "components").mkdir(parents=True)

    # Create a source file in a sibling dir with no .git
    code_dir = tmp_path / "code-no-git" / "src"
    code_dir.mkdir(parents=True)
    (code_dir / "app.py").write_text("# code")

    # Write a valid doc that describes the cross-repo source
    (docs_root / "docs" / "components" / "app.md").write_text(
        "---\nid: app\ntitle: App\nstatus: stable\ndescribes:\n  - app.py\n---\n\n# App\n"
    )

    # Write irminsul.toml pointing at the sibling code dir
    rel_source = Path("../code-no-git/src").as_posix()
    (docs_root / "irminsul.toml").write_text(
        f'project_name = "test"\n[paths]\ndocs_root = "docs"\nsource_roots = ["{rel_source}"]\n'
    )

    from irminsul.config import find_config, load

    config = load(find_config(docs_root))
    # Enable mtime-drift
    config = config.model_copy(
        update={"checks": config.checks.model_copy(update={"enabled": ["mtime-drift"]})}
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
    mono = tmp_path / "mono"
    proj = mono / "packages" / "proj"
    (proj / "docs").mkdir(parents=True)
    (proj / "docs" / "d.md").write_text("# d\n", encoding="utf-8")

    return proj, seed_repo(mono, "monorepo")


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

    result = last_commit_time_any_repo(GitReader(), doc, proj)

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
    outer_root = tmp_path / "project"
    vendored = outer_root / "vendor" / "lib"
    vendored.mkdir(parents=True)
    tracked = vendored / "core.py"
    tracked.write_text("x = 1\n", encoding="utf-8")

    outer_sha = seed_repo(outer_root, "vendored code was once ours")
    git(outer_root, "rm", "-r", "--cached", "vendor/lib")
    git(outer_root, "commit", "-qm", "hand it to its own repository")

    inner_sha = seed_repo(vendored, "its own history")

    result = last_commit_time_any_repo(GitReader(), tracked, outer_root)

    assert result is not None
    assert result.sha == inner_sha
    assert result.sha != outer_sha


def test_uncommitted_files_in_sibling_repositories_share_the_pending_instant(
    tmp_path: Path,
) -> None:
    """A doc edited in the docs repository and the source it cites edited in the code
    repository read as changed together, so neither is after the other."""
    docs, code = tmp_path / "docs-repo", tmp_path / "code-repo"
    for repo, rel in ((docs, "d.md"), (code, "app.py")):
        repo.mkdir()
        (repo / rel).write_text("one\n", encoding="utf-8")
        seed_repo(repo, "seed", when="2025-01-01T12:00:00")
    (docs / "d.md").write_text("two\n", encoding="utf-8")
    (code / "app.py").write_text("two\n", encoding="utf-8")
    pending = pending_time(_dt.date(2025, 2, 1))
    reader = GitReader(pending=pending)

    assert last_commit_time_any_repo(reader, docs / "d.md", docs) == pending
    assert last_commit_time_any_repo(reader, code / "app.py", docs) == pending


def test_uncommitted_work_below_an_enclosing_repository_is_pending(tmp_path: Path) -> None:
    proj, _ = _monorepo(tmp_path)
    doc = proj / "docs" / "d.md"
    doc.write_text("# d\n\nedited\n", encoding="utf-8")
    pending = pending_time(_dt.date(2025, 2, 1))

    assert last_commit_time_any_repo(GitReader(pending=pending), doc, proj) == pending
    assert last_commit_time_any_repo(GitReader(), doc, proj) != pending


def test_asking_the_invocation_root_alone_would_lose_the_history(tmp_path: Path) -> None:
    """The mirror, and the reason the branch cannot be collapsed: resolving
    against the invocation root instead of the enclosing repo yields no history
    at all, so every git time would silently vanish."""
    from irminsul.git.mtime import _bulk_lookup

    proj, _ = _monorepo(tmp_path)
    doc = proj / "docs" / "d.md"

    assert _bulk_lookup(GitReader(), proj, doc) == GitTime(sha=None, when=None)
