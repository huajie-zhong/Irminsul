"""Tests for `StaleReaperCheck`.

The check uses the doc's git commit time rather than a manually maintained
field, so tests bootstrap small git repos with controlled commit dates.
"""

from __future__ import annotations

import datetime as _dt
from pathlib import Path

from git import Repo

from irminsul.checks.stale_reaper import StaleReaperCheck
from irminsul.config import find_config, load
from irminsul.docgraph import build_graph

_THRESHOLD = 90


def _bootstrap(
    tmp_path: Path,
    *,
    status: str,
    committed_days_ago: int,
) -> Path:
    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    repo = Repo.init(repo_root)
    with repo.config_writer() as cw:
        cw.set_value("user", "name", "Test")
        cw.set_value("user", "email", "test@example.com")

    doc = repo_root / "docs" / "20-components" / "widget.md"
    doc.parent.mkdir(parents=True)
    doc.write_text(
        "---\n"
        "id: widget\n"
        "title: Widget\n"
        "audience: explanation\n"
        "tier: 3\n"
        f"status: {status}\n"
        "---\n\n# Widget\n",
        encoding="utf-8",
    )
    (repo_root / "irminsul.toml").write_text(
        'project_name = "stale-test"\n'
        '[paths]\ndocs_root = "docs"\nsource_roots = []\n'
        '[checks]\nsoft_deterministic = ["stale-reaper"]\n'
        f"[checks.stale_reaper]\ndeprecated_threshold_days = {_THRESHOLD}\n",
        encoding="utf-8",
    )

    commit_date = _dt.datetime.now(_dt.UTC) - _dt.timedelta(days=committed_days_ago)
    repo.index.add(["docs/20-components/widget.md", "irminsul.toml"])
    repo.index.commit("init", author_date=commit_date, commit_date=commit_date)
    repo.close()
    return repo_root


def test_old_deprecated_doc_flagged(tmp_path: Path) -> None:
    repo = _bootstrap(tmp_path, status="deprecated", committed_days_ago=_THRESHOLD + 30)
    graph = build_graph(repo, load(find_config(repo)))
    findings = StaleReaperCheck().run(graph)
    assert any(f.doc_id == "widget" for f in findings)


def test_recent_deprecation_not_flagged(tmp_path: Path) -> None:
    repo = _bootstrap(tmp_path, status="deprecated", committed_days_ago=5)
    graph = build_graph(repo, load(find_config(repo)))
    findings = StaleReaperCheck().run(graph)
    assert not findings


def test_stable_doc_not_flagged(tmp_path: Path) -> None:
    repo = _bootstrap(tmp_path, status="stable", committed_days_ago=_THRESHOLD + 30)
    graph = build_graph(repo, load(find_config(repo)))
    findings = StaleReaperCheck().run(graph)
    assert not findings


def test_finding_carries_suggestion(tmp_path: Path) -> None:
    repo = _bootstrap(tmp_path, status="deprecated", committed_days_ago=_THRESHOLD + 30)
    graph = build_graph(repo, load(find_config(repo)))
    findings = StaleReaperCheck().run(graph)
    stale = next(f for f in findings if f.doc_id == "widget")
    assert stale.suggestion is not None
    assert "remove" in stale.suggestion or "rewrite" in stale.suggestion
