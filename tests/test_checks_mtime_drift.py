"""Tests for `MtimeDriftCheck`.

The check needs real git history, so each test bootstraps a small repo in
`tmp_path` rather than reading a static fixture.
"""

from __future__ import annotations

import datetime as _dt
from pathlib import Path

from git import Repo

from irminsul.checks.mtime_drift import MtimeDriftCheck
from irminsul.config import IrminsulConfig
from irminsul.docgraph import build_graph


def _bootstrap(tmp_path: Path, *, doc_old: bool = False, source_content: str = "x = 1\n") -> Path:
    """Create a git repo with one source file and one doc.

    doc_old=True: doc committed with old date (2024-01-01), source committed
    with current date. Produces >30 days of drift.
    doc_old=False: both committed at the same time. Drift = 0.
    """
    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    repo = Repo.init(repo_root)
    with repo.config_writer() as cw:
        cw.set_value("user", "name", "Test")
        cw.set_value("user", "email", "test@example.com")

    src = repo_root / "app" / "thing.py"
    src.parent.mkdir(parents=True)
    src.write_text(source_content, encoding="utf-8")

    doc = repo_root / "docs" / "20-components" / "thing.md"
    doc.parent.mkdir(parents=True)
    doc.write_text(
        "---\n"
        "id: thing\n"
        "title: Thing\n"
        "audience: explanation\n"
        "tier: 3\n"
        "status: stable\n"
        "describes:\n"
        "  - app/thing.py\n"
        "---\n\n# Thing\n",
        encoding="utf-8",
    )

    config_toml = repo_root / "irminsul.toml"
    config_toml.write_text(
        'project_name = "mtime-drift-test"\n'
        '[paths]\ndocs_root = "docs"\nsource_roots = ["app"]\n'
        '[checks]\nsoft_deterministic = ["mtime-drift"]\n'
        "[overrides]\nmtime_drift_days = 30\n",
        encoding="utf-8",
    )

    if doc_old:
        old = _dt.datetime(2024, 1, 1, tzinfo=_dt.UTC)
        repo.index.add(["docs/20-components/thing.md", "irminsul.toml"])
        repo.index.commit("doc", author_date=old, commit_date=old)
        repo.index.add(["app/thing.py"])
        repo.index.commit("source")
    else:
        repo.index.add(["app/thing.py", "docs/20-components/thing.md", "irminsul.toml"])
        repo.index.commit("seed")

    repo.close()
    return repo_root


def test_drift_flagged_when_doc_lags(tmp_path: Path) -> None:
    repo_root = _bootstrap(tmp_path, doc_old=True)
    from irminsul.config import find_config, load

    config = load(find_config(repo_root))
    graph = build_graph(repo_root, config)

    findings = MtimeDriftCheck().run(graph)
    assert any(f.doc_id == "thing" for f in findings)
    finding = next(f for f in findings if f.doc_id == "thing")
    assert finding.severity.value == "warning"
    assert finding.suggestion is not None
    assert "doc last committed" in finding.message


def test_no_drift_when_recent(tmp_path: Path) -> None:
    repo_root = _bootstrap(tmp_path, doc_old=False)
    from irminsul.config import find_config, load

    config = load(find_config(repo_root))
    graph = build_graph(repo_root, config)

    findings = MtimeDriftCheck().run(graph)
    assert not findings


def test_doc_without_describes_skipped(tmp_path: Path) -> None:
    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    repo = Repo.init(repo_root)
    with repo.config_writer() as cw:
        cw.set_value("user", "name", "Test")
        cw.set_value("user", "email", "test@example.com")

    doc = repo_root / "docs" / "10-architecture" / "overview.md"
    doc.parent.mkdir(parents=True)
    doc.write_text(
        "---\nid: overview\ntitle: Overview\naudience: explanation\ntier: 2\n"
        "status: stable\n---\n\n# Overview\n",
        encoding="utf-8",
    )
    (repo_root / "irminsul.toml").write_text(
        'project_name = "no-describes"\n'
        '[paths]\ndocs_root = "docs"\nsource_roots = []\n'
        '[checks]\nsoft_deterministic = ["mtime-drift"]\n',
        encoding="utf-8",
    )
    repo.index.add(["docs/10-architecture/overview.md", "irminsul.toml"])
    repo.index.commit("seed")
    repo.close()

    config = IrminsulConfig()
    graph = build_graph(repo_root, config)
    findings = MtimeDriftCheck().run(graph)
    assert not findings


def test_no_git_history_skips_silently(tmp_path: Path) -> None:
    """When no git history exists, the check returns no findings rather than
    erroring. Lets `irminsul check` work on tarball checkouts."""
    repo_root = tmp_path / "norepo"
    repo_root.mkdir()
    (repo_root / "app").mkdir()
    (repo_root / "app" / "thing.py").write_text("x = 1\n", encoding="utf-8")
    docs = repo_root / "docs" / "20-components"
    docs.mkdir(parents=True)
    (docs / "thing.md").write_text(
        "---\nid: thing\ntitle: Thing\naudience: explanation\ntier: 3\n"
        "status: stable\n"
        "describes:\n  - app/thing.py\n---\n\n# Thing\n",
        encoding="utf-8",
    )
    (repo_root / "irminsul.toml").write_text(
        'project_name = "norepo"\n'
        '[paths]\ndocs_root = "docs"\nsource_roots = ["app"]\n'
        '[checks]\nsoft_deterministic = ["mtime-drift"]\n',
        encoding="utf-8",
    )

    from irminsul.config import find_config, load

    config = load(find_config(repo_root))
    graph = build_graph(repo_root, config)
    findings = MtimeDriftCheck().run(graph)
    assert not findings
