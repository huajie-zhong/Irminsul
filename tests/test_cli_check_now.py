"""CLI tests for the `irminsul check --now` date override.

`--now` feeds date-sensitive checks a fixed "today"; stale-reaper compares it
against the doc's git commit time, so a doc committed just now only fires when
the clock is overridden past the threshold.
"""

from __future__ import annotations

import datetime as _dt
from pathlib import Path

from git import Repo
from typer.testing import CliRunner

from irminsul.cli import app

runner = CliRunner()

_THRESHOLD = 90


def _deprecated_doc_repo(tmp_path: Path) -> Path:
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
        "status: deprecated\n"
        "---\n\n# Widget\n",
        encoding="utf-8",
    )
    (repo_root / "irminsul.toml").write_text(
        'project_name = "now-test"\n'
        '[paths]\ndocs_root = "docs"\nsource_roots = []\n'
        '[checks]\nhard = ["frontmatter"]\nsoft_deterministic = ["stale-reaper"]\n'
        f"[checks.stale_reaper]\ndeprecated_threshold_days = {_THRESHOLD}\n",
        encoding="utf-8",
    )

    repo.index.add(["docs/20-components/widget.md", "irminsul.toml"])
    repo.index.commit("init")
    repo.close()
    return repo_root


def test_check_now_overrides_today_for_stale_reaper(tmp_path: Path) -> None:
    repo = _deprecated_doc_repo(tmp_path)
    future = (_dt.date.today() + _dt.timedelta(days=_THRESHOLD + 30)).isoformat()

    aged = runner.invoke(
        app,
        ["check", "--profile", "configured", "--path", str(repo), "--now", future],
    )
    assert aged.exit_code == 0, aged.output
    assert "[stale-reaper]" in aged.output

    # Without the override the doc was committed "today" and is not stale.
    current = runner.invoke(app, ["check", "--profile", "configured", "--path", str(repo)])
    assert current.exit_code == 0, current.output
    assert "[stale-reaper]" not in current.output


def test_check_now_rejects_invalid_date(tmp_path: Path) -> None:
    result = runner.invoke(app, ["check", "--path", str(tmp_path), "--now", "not-a-date"])
    assert result.exit_code == 2
    assert "expected YYYY-MM-DD" in result.output
