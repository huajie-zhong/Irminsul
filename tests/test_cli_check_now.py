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

    doc = repo_root / "docs" / "components" / "widget.md"
    doc.parent.mkdir(parents=True)
    doc.write_text(
        "---\nid: widget\ntitle: Widget\nstatus: deprecated\n---\n\n# Widget\n",
        encoding="utf-8",
    )
    (repo_root / "irminsul.toml").write_text(
        'project_name = "now-test"\n'
        '[paths]\ndocs_root = "docs"\nsource_roots = []\n'
        '[checks]\nenabled = ["frontmatter", "stale-reaper"]\n'
        f"[checks.stale_reaper]\ndeprecated_threshold_days = {_THRESHOLD}\n",
        encoding="utf-8",
    )

    repo.index.add(["docs/components/widget.md", "irminsul.toml"])
    repo.index.commit("init")
    repo.close()
    return repo_root


def test_check_now_overrides_today_for_stale_reaper(tmp_path: Path) -> None:
    repo = _deprecated_doc_repo(tmp_path)
    future = (_dt.date.today() + _dt.timedelta(days=_THRESHOLD + 30)).isoformat()

    aged = runner.invoke(
        app,
        ["check", "--path", str(repo), "--now", future],
    )
    assert aged.exit_code == 0, aged.output
    assert "[stale-reaper/stale-deprecated-doc]" in aged.output

    # Without the override the doc was committed "today" and is not stale.
    current = runner.invoke(app, ["check", "--path", str(repo)])
    assert current.exit_code == 0, current.output
    assert "[stale-reaper/stale-deprecated-doc]" not in current.output


def test_check_now_rejects_invalid_date(tmp_path: Path) -> None:
    result = runner.invoke(app, ["check", "--path", str(tmp_path), "--now", "not-a-date"])
    assert result.exit_code == 2
    assert "expected YYYY-MM-DD" in result.output


def test_fail_on_adds_classes_to_the_time_findings_it_names(tmp_path: Path) -> None:
    repo = _deprecated_doc_repo(tmp_path)
    future = (_dt.date.today() + _dt.timedelta(days=_THRESHOLD + 30)).isoformat()
    base = ["check", "--path", str(repo), "--now", future]

    assert runner.invoke(app, [*base, "--fail-on", "time"]).exit_code == 1
    assert runner.invoke(app, [*base, "--fail-on", "certain,hint"]).exit_code == 0
    assert runner.invoke(app, ["check", "--path", str(repo), "--fail-on", "time"]).exit_code == 0


def test_fail_on_cannot_turn_the_certain_gate_off(tmp_path: Path) -> None:
    repo = _deprecated_doc_repo(tmp_path)
    (repo / "docs" / "components" / "widget.md").write_text(
        "---\nid: widget\ntitle: Widget\n---\n\n# Widget\n", encoding="utf-8"
    )

    plain = runner.invoke(app, ["check", "--path", str(repo)])
    assert plain.exit_code == 1, plain.output

    for named in ("time", "hint", "hint,time"):
        narrowed = runner.invoke(app, ["check", "--path", str(repo), "--fail-on", named])
        assert narrowed.exit_code == 1, f"--fail-on {named} let a certain finding pass"


def test_fail_on_rejects_unknown_classes_and_strict(tmp_path: Path) -> None:
    repo = _deprecated_doc_repo(tmp_path)
    base = ["check", "--path", str(repo)]
    assert runner.invoke(app, [*base, "--fail-on", "sometimes"]).exit_code == 2
    assert runner.invoke(app, [*base, "--fail-on", "time", "--strict"]).exit_code == 2
