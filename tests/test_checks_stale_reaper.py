"""Tests for `StaleReaperCheck`.

The check uses the doc's git commit time rather than a manually maintained
field, so tests bootstrap small git repos with controlled commit dates.
"""

from __future__ import annotations

import datetime as _dt
from pathlib import Path

from irminsul.checks.base import Finding
from irminsul.checks.stale_reaper import StaleReaperCheck

from .conftest import run_check, seed_repo, write, write_config

_THRESHOLD = 90
_COMMITTED = _dt.datetime(2025, 1, 1, tzinfo=_dt.UTC)


def _bootstrap(tmp_path: Path, *, status: str) -> Path:
    repo_root = tmp_path / "repo"
    write(
        repo_root,
        "docs/components/widget.md",
        f"---\nid: widget\ntitle: Widget\nstatus: {status}\n---\n\n# Widget\n",
    )
    write_config(
        repo_root,
        project_name="stale-test",
        enabled=["stale-reaper"],
        extra=f"[checks.stale_reaper]\ndeprecated_threshold_days = {_THRESHOLD}\n",
    )
    seed_repo(repo_root, "init", when=_COMMITTED)
    return repo_root


def _findings(repo: Path, *, age_days: int, **graph_kwargs: object) -> list[Finding]:
    """The check's findings on the day the doc's last commit is `age_days` old."""
    today = (_COMMITTED + _dt.timedelta(days=age_days)).date()
    return run_check(StaleReaperCheck, repo, now=today, **graph_kwargs)


def test_old_deprecated_doc_flagged(tmp_path: Path) -> None:
    repo = _bootstrap(tmp_path, status="deprecated")
    findings = _findings(repo, age_days=_THRESHOLD + 30)
    assert any(f.doc_id == "widget" for f in findings)


def test_recent_deprecation_not_flagged(tmp_path: Path) -> None:
    repo = _bootstrap(tmp_path, status="deprecated")
    findings = _findings(repo, age_days=5)
    assert not findings


def test_stable_doc_not_flagged(tmp_path: Path) -> None:
    repo = _bootstrap(tmp_path, status="stable")
    findings = _findings(repo, age_days=_THRESHOLD + 30)
    assert not findings


def test_finding_carries_suggestion(tmp_path: Path) -> None:
    repo = _bootstrap(tmp_path, status="deprecated")
    findings = _findings(repo, age_days=_THRESHOLD + 30)
    stale = next(f for f in findings if f.doc_id == "widget")
    assert stale.suggestion is not None
    assert "remove" in stale.suggestion or "rewrite" in stale.suggestion


def test_an_uncommitted_edit_resets_a_deprecated_docs_age(tmp_path: Path) -> None:
    """The edit is the commit that would reset it, so the run reports what that commit will."""
    repo = _bootstrap(tmp_path, status="deprecated")
    assert _findings(repo, age_days=_THRESHOLD + 30)

    doc = repo / "docs" / "components" / "widget.md"
    doc.write_text(doc.read_text(encoding="utf-8") + "\nSuperseded.\n", encoding="utf-8")

    assert _findings(repo, age_days=_THRESHOLD + 30) == []
    assert _findings(repo, age_days=_THRESHOLD + 30, committed_only=True)
