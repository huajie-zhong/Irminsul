"""Unit tests for the derived layered impact report (RFC-0033)."""

from __future__ import annotations

import json
import subprocess
from collections.abc import Callable
from pathlib import Path

import pytest
from typer.testing import CliRunner

from irminsul.change.impact import (
    build_impact_report,
    format_impact_plain,
    impact_report_to_json,
    impact_summary,
)
from irminsul.cli import app
from irminsul.config import find_config, load

runner = CliRunner()

_RFC = "0001-accepted-good"


@pytest.fixture
def repo(fixture_repo: Callable[[str], Path]) -> Path:
    return fixture_repo("soft-change-binding")


def _git_init(repo: Path) -> None:
    for args in (
        ("init", "-q"),
        ("config", "user.email", "t@example.com"),
        ("config", "user.name", "T"),
        ("add", "."),
        ("commit", "-q", "-m", "init"),
    ):
        subprocess.run(["git", "-C", str(repo), *args], check=True, capture_output=True)


def test_plan_impact_without_git(repo: Path) -> None:
    report = build_impact_report(repo, load(find_config(repo)), _RFC, env={})
    assert report.level == "plan"
    assert report.baseline.changed_paths is None

    components = [o.observation for o in report.layers["components"]]
    assert any("'auth'" in text for text in components)
    assert any("behavioral requirement" in text for text in components)

    workflows = report.layers["workflows"]
    assert any("login-flow" in o.observation for o in workflows)
    assert all(o.review for o in workflows)

    decisions = [o.observation for o in report.layers["decisions"]]
    assert any("docs/50-decisions/0001-adr.md" in text for text in decisions)


def test_plan_impact_no_direction_no_foundation(repo: Path) -> None:
    report = build_impact_report(repo, load(find_config(repo)), _RFC, env={})
    assert report.layers["foundation"] == []


def test_revises_direction_creates_foundation_clue(repo: Path) -> None:
    path = repo / "docs" / "80-evolution" / "rfcs" / f"{_RFC}.md"
    text = path.read_text(encoding="utf-8")
    path.write_text(
        text.replace("rfc_state: accepted", "rfc_state: accepted\ndirection: revises"),
        encoding="utf-8",
    )
    report = build_impact_report(repo, load(find_config(repo)), _RFC, env={})
    [observation] = report.layers["foundation"]
    assert "revises" in observation.observation
    assert observation.source == "rfc:direction"
    assert observation.review is not None


def test_observed_impact_reports_divergence(repo: Path) -> None:
    _git_init(repo)
    (repo / "app" / "billing" / "extra.py").write_text("x = 1\n", encoding="utf-8")
    report = build_impact_report(repo, load(find_config(repo)), _RFC, env={})
    assert report.level == "observed"

    components = report.layers["components"]
    billing = [o for o in components if "'billing'" in o.observation]
    assert billing and any("absent from `affects`" in o.observation for o in billing)
    assert any(o.review for o in billing)
    assert any(
        "'auth'" in o.observation and "no owned source change" in o.observation for o in components
    )


def test_observed_impact_lists_changed_docs_by_layer(repo: Path) -> None:
    _git_init(repo)
    workflow = repo / "docs" / "30-workflows" / "login-flow.md"
    workflow.write_text(workflow.read_text(encoding="utf-8") + "\nUpdated.\n", encoding="utf-8")
    report = build_impact_report(repo, load(find_config(repo)), _RFC, env={})
    assert any(
        "docs/30-workflows/login-flow.md" in o.observation for o in report.layers["workflows"]
    )


def test_impact_summary_counts_only_nonempty_layers(repo: Path) -> None:
    report = build_impact_report(repo, load(find_config(repo)), _RFC, env={})
    summary = impact_summary(report)
    assert summary["components"] >= 1
    assert "foundation" not in summary


def test_impact_json_round_trips(repo: Path) -> None:
    report = build_impact_report(repo, load(find_config(repo)), _RFC, env={})
    data = json.loads(impact_report_to_json(report))
    assert data["version"] == 1
    assert data["level"] == "plan"
    assert "components" in data["layers"]
    assert "foundation" not in data["layers"]

    full = json.loads(impact_report_to_json(report, all_layers=True))
    assert "foundation" in full["layers"]


def test_impact_plain_states_plan_level(repo: Path) -> None:
    report = build_impact_report(repo, load(find_config(repo)), _RFC, env={})
    plain = format_impact_plain(report)
    assert "impact (plan)" in plain
    assert "observed impact unavailable, not empty" in plain


def test_cli_change_impact(repo: Path) -> None:
    result = runner.invoke(
        app,
        ["change", "impact", _RFC, "--format", "json", "--path", str(repo)],
    )
    assert result.exit_code == 0, result.output
    data = json.loads(result.output)
    assert data["change"] == _RFC


def test_cli_change_impact_unknown_id(repo: Path) -> None:
    result = runner.invoke(app, ["change", "impact", "nope", "--path", str(repo)])
    assert result.exit_code == 2


def test_status_embeds_impact_summary(repo: Path) -> None:
    result = runner.invoke(
        app,
        ["change", "status", _RFC, "--format", "json", "--path", str(repo)],
    )
    assert result.exit_code == 0, result.output
    data = json.loads(result.output)
    assert data["impact"]["level"] == "plan"
    assert data["impact"]["summary"]["components"] >= 1
