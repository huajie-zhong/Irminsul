"""Tests for `MtimeDriftCheck`.

The check needs real git history, so each test bootstraps a small repo in
`tmp_path` rather than reading a static fixture.
"""

from __future__ import annotations

import datetime as _dt
from pathlib import Path

from irminsul.checks.mtime_drift import MtimeDriftCheck
from irminsul.config import IrminsulConfig
from irminsul.docgraph import build_graph

from .conftest import commit_all, git_init, run_check, write_config


def _bootstrap(tmp_path: Path, *, doc_old: bool = False, source_content: str = "x = 1\n") -> Path:
    """Create a git repo with one source file and one doc.

    doc_old=True: doc committed on 2024-01-01, source committed on 2024-06-01.
    Produces >30 days of drift.
    doc_old=False: both committed on 2024-01-01. Drift = 0.
    """
    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    git_init(repo_root)

    src = repo_root / "app" / "thing.py"
    src.parent.mkdir(parents=True)
    src.write_text(source_content, encoding="utf-8")

    doc = repo_root / "docs" / "components" / "thing.md"
    doc.parent.mkdir(parents=True)
    doc.write_text(
        "---\n"
        "id: thing\n"
        "title: Thing\n"
        ""
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
        '[checks]\nenabled = ["mtime-drift"]\n'
        "[overrides]\nmtime_drift_days = 30\n",
        encoding="utf-8",
    )

    if doc_old:
        old = _dt.datetime(2024, 1, 1, tzinfo=_dt.UTC)
        commit_all(repo_root, "doc", when=old, paths=["docs/components/thing.md", "irminsul.toml"])
        commit_all(
            repo_root,
            "source",
            when=_dt.datetime(2024, 6, 1, tzinfo=_dt.UTC),
            paths=["app/thing.py"],
        )
    else:
        commit_all(repo_root, "seed", when=_dt.datetime(2024, 1, 1, tzinfo=_dt.UTC))

    return repo_root


def test_drift_flagged_when_doc_lags(tmp_path: Path) -> None:
    repo_root = _bootstrap(tmp_path, doc_old=True)

    findings = run_check(MtimeDriftCheck, repo_root)
    assert any(f.doc_id == "thing" for f in findings)
    finding = next(f for f in findings if f.doc_id == "thing")
    assert finding.severity.value == "warning"
    assert finding.suggestion is not None
    assert "doc last committed" in finding.message


def test_no_drift_when_recent(tmp_path: Path) -> None:
    repo_root = _bootstrap(tmp_path, doc_old=False)

    findings = run_check(MtimeDriftCheck, repo_root)
    assert not findings


_NOW = _dt.date(2024, 9, 1)


def _messages(repo_root: Path, **graph_kwargs: object) -> list[str]:
    return [f.message for f in run_check(MtimeDriftCheck, repo_root, now=_NOW, **graph_kwargs)]


def _edit(repo_root: Path, rel: str, extra: str) -> None:
    path = repo_root / rel
    path.write_text(path.read_text(encoding="utf-8") + extra, encoding="utf-8")


def test_an_uncommitted_edit_to_a_source_counts_as_changed_today(tmp_path: Path) -> None:
    repo_root = _bootstrap(tmp_path, doc_old=False)
    assert _messages(repo_root) == []

    _edit(repo_root, "app/thing.py", "y = 2\n")

    assert _messages(repo_root) == [
        "source last touched 2024-09-01; doc last committed 2024-01-01 "
        "(244 days drift, threshold 30)"
    ]
    assert _messages(repo_root, committed_only=True) == []


def test_editing_the_doc_answers_committed_drift_before_the_commit(tmp_path: Path) -> None:
    repo_root = _bootstrap(tmp_path, doc_old=True)
    assert len(_messages(repo_root)) == 1

    _edit(repo_root, "docs/components/thing.md", "\nRe-read against the source.\n")

    assert _messages(repo_root) == []
    assert len(_messages(repo_root, committed_only=True)) == 1


def test_a_doc_and_its_source_both_edited_do_not_drift(tmp_path: Path) -> None:
    repo_root = _bootstrap(tmp_path, doc_old=False)

    _edit(repo_root, "app/thing.py", "y = 2\n")
    _edit(repo_root, "docs/components/thing.md", "\nIt sets y.\n")

    assert _messages(repo_root) == []


def test_doc_without_describes_skipped(tmp_path: Path) -> None:
    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    git_init(repo_root)

    doc = repo_root / "docs" / "architecture" / "overview.md"
    doc.parent.mkdir(parents=True)
    doc.write_text(
        "---\nid: overview\ntitle: Overview\nstatus: stable\n---\n\n# Overview\n",
        encoding="utf-8",
    )
    write_config(repo_root, project_name="no-describes", enabled=["mtime-drift"])
    commit_all(repo_root, "seed")

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
    docs = repo_root / "docs" / "components"
    docs.mkdir(parents=True)
    (docs / "thing.md").write_text(
        "---\nid: thing\ntitle: Thing\n"
        "status: stable\n"
        "describes:\n  - app/thing.py\n---\n\n# Thing\n",
        encoding="utf-8",
    )
    write_config(repo_root, project_name="norepo", source_roots=["app"], enabled=["mtime-drift"])

    findings = run_check(MtimeDriftCheck, repo_root)
    assert not findings
