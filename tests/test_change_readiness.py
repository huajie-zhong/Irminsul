"""Tests for binding readiness and the RFC-0034 report extensions."""

from __future__ import annotations

import json
import subprocess
from collections.abc import Callable
from pathlib import Path

import pytest
from typer.testing import CliRunner

from irminsul.change.readiness import (
    binding_readiness_to_json,
    build_binding_readiness_report,
    format_binding_readiness_plain,
)
from irminsul.change.report import build_change_report, change_report_to_json
from irminsul.cli import app
from irminsul.config import find_config, load

runner = CliRunner()

_BAD_FRONTMATTER = Path(__file__).parent / "fixtures" / "repos" / "bad-frontmatter"


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


def test_readiness_clean_repo_is_ready(repo: Path) -> None:
    report = build_binding_readiness_report(repo, load(find_config(repo)))
    assert report.ready
    assert report.blockers == ()


def test_readiness_hard_errors_block() -> None:
    report = build_binding_readiness_report(_BAD_FRONTMATTER, load(find_config(_BAD_FRONTMATTER)))
    assert not report.ready
    assert report.blockers
    assert all(item.check for item in report.blockers)


def test_readiness_json_shape(repo: Path) -> None:
    report = build_binding_readiness_report(repo, load(find_config(repo)))
    data = json.loads(binding_readiness_to_json(report))
    assert data["version"] == 1
    assert data["ready"] is True
    assert isinstance(data["clues"], list)
    assert isinstance(data["repository_debt"], list)


def test_readiness_plain_output(repo: Path) -> None:
    report = build_binding_readiness_report(repo, load(find_config(repo)))
    assert "binding readiness: ready" in format_binding_readiness_plain(report)


def test_new_rfc_blocked_by_hard_errors(fixture_repo: Callable[[str], Path]) -> None:
    repo = fixture_repo("bad-frontmatter")
    result = runner.invoke(app, ["new", "rfc", "Blocked Idea", "--path", str(repo)])
    assert result.exit_code == 1
    assert "hard checks fail" in result.output
    assert not list((repo / "docs").glob("80-evolution/rfcs/*blocked-idea*"))


def test_new_rfc_force_overrides_block(fixture_repo: Callable[[str], Path]) -> None:
    repo = fixture_repo("bad-frontmatter")
    result = runner.invoke(app, ["new", "rfc", "Forced Idea", "--force", "--path", str(repo)])
    assert result.exit_code == 0, result.output
    assert "created:" in result.output


def test_new_rfc_proceeds_when_ready(repo: Path) -> None:
    result = runner.invoke(app, ["new", "rfc", "Good Idea", "--path", str(repo)])
    assert result.exit_code == 0, result.output
    assert "created:" in result.output


def test_report_carries_repository_debt_key(repo: Path) -> None:
    _git_init(repo)
    report = build_change_report(repo, load(find_config(repo)), "0001-accepted-good", env={})
    data = json.loads(change_report_to_json(report))
    assert "repository_debt" in data
    assert isinstance(data["repository_debt"], list)


def test_report_blocks_on_unresolved_required_update(repo: Path) -> None:
    _git_init(repo)
    rfc = repo / "docs" / "80-evolution" / "rfcs" / "0001-accepted-good.md"
    text = rfc.read_text(encoding="utf-8")
    rfc.write_text(
        text.replace(
            "required_updates: []",
            "required_updates:\n  - path: docs/30-workflows/missing.md\n    kind: update",
        ),
        encoding="utf-8",
    )
    report = build_change_report(repo, load(find_config(repo)), "0001-accepted-good", env={})
    assert any(b.code.startswith("decision-updates:") for b in report.blockers)
    assert report.mechanically_ready_for == "none"


def test_lifecycle_queue_includes_accepted_backlog(repo: Path) -> None:
    result = runner.invoke(
        app,
        ["list", "lifecycle", "--queue", "--format", "json", "--path", str(repo)],
    )
    assert result.exit_code == 0, result.output
    data = json.loads(result.output)
    backlog = [item for item in data if item["kind"] == "implement"]
    assert {item["related_id"] for item in backlog} == {
        "0001-accepted-good",
        "0002-accepted-missing-affects",
    }
    assert all(item["suggested_command"].startswith("irminsul change status") for item in backlog)
