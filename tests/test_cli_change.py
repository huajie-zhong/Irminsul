"""Tests for the `irminsul change` command group (RFC-0029)."""

from __future__ import annotations

import json
from collections.abc import Callable
from pathlib import Path

import pytest
from typer.testing import CliRunner

from irminsul.cli import app

runner = CliRunner()

_ADR = "docs/50-decisions/0001-adr.md"


@pytest.fixture
def repo(fixture_repo: Callable[[str], Path]) -> Path:
    return fixture_repo("soft-change-binding")


def test_change_status_json(repo: Path) -> None:
    result = runner.invoke(
        app,
        ["change", "status", "0001-accepted-good", "--format", "json", "--path", str(repo)],
    )
    assert result.exit_code == 0, result.output
    data = json.loads(result.output)
    assert data["change"] == "0001-accepted-good"
    assert data["state"] == "accepted"
    assert "mechanically_ready_for" in data


def test_change_status_unknown_id(repo: Path) -> None:
    result = runner.invoke(app, ["change", "status", "nope", "--path", str(repo)])
    assert result.exit_code == 2
    assert "no RFC found" in result.output


def test_change_verify_json(repo: Path) -> None:
    result = runner.invoke(
        app,
        ["change", "verify", "0004-draft-ready", "--format", "json", "--path", str(repo)],
    )
    assert result.exit_code == 0, result.output
    data = json.loads(result.output)
    assert isinstance(data["blockers"], list)
    assert isinstance(data["semantic_review"], list)


def test_change_transition_plan_only(repo: Path) -> None:
    rfc = repo / "docs" / "80-evolution" / "rfcs" / "0004-draft-ready.md"
    before = rfc.read_text(encoding="utf-8")
    result = runner.invoke(
        app,
        [
            "change",
            "transition",
            "0004-draft-ready",
            "accepted",
            "--resolved-by",
            _ADR,
            "--path",
            str(repo),
        ],
    )
    assert result.exit_code == 0, result.output
    assert "--confirm" in result.output
    assert rfc.read_text(encoding="utf-8") == before


def test_change_transition_confirm_applies(repo: Path) -> None:
    rfc = repo / "docs" / "80-evolution" / "rfcs" / "0004-draft-ready.md"
    result = runner.invoke(
        app,
        [
            "change",
            "transition",
            "0004-draft-ready",
            "accepted",
            "--resolved-by",
            _ADR,
            "--confirm",
            "--path",
            str(repo),
        ],
    )
    assert result.exit_code == 0, result.output
    assert "updated" in result.output
    text = rfc.read_text(encoding="utf-8")
    assert "rfc_state: accepted" in text
    assert "status: stable" in text


def test_change_transition_blocked_exits_one(repo: Path) -> None:
    result = runner.invoke(
        app,
        ["change", "transition", "0001-accepted-good", "accepted", "--path", str(repo)],
    )
    assert result.exit_code == 1
    assert "invalid-transition" in result.output


def test_change_transition_rejects_implemented_target(repo: Path) -> None:
    result = runner.invoke(
        app,
        ["change", "transition", "0004-draft-ready", "implemented", "--path", str(repo)],
    )
    assert result.exit_code == 2
