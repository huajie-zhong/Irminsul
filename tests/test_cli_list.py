"""Tests for `irminsul list orphans/stale/undocumented`."""

from __future__ import annotations

import json
from pathlib import Path

from typer.testing import CliRunner

from irminsul.checks.base import Finding, Severity
from irminsul.cli import app
from irminsul.listing.command import _to_queue_item

runner = CliRunner()

_ORPHAN_FIXTURE = Path(__file__).parent / "fixtures" / "repos" / "soft-orphans"
_STALE_FIXTURE = Path(__file__).parent / "fixtures" / "repos" / "soft-stale-reaper"
_LIFECYCLE_FIXTURE = Path(__file__).parent / "fixtures" / "repos" / "soft-lifecycle"


def test_list_orphans_plain(tmp_path: Path) -> None:
    result = runner.invoke(app, ["list", "orphans", "--path", str(_ORPHAN_FIXTURE)])
    assert result.exit_code == 0, result.output
    assert len(result.output.strip().splitlines()) >= 1


def test_list_orphans_json(tmp_path: Path) -> None:
    result = runner.invoke(
        app, ["list", "orphans", "--format", "json", "--path", str(_ORPHAN_FIXTURE)]
    )
    assert result.exit_code == 0, result.output
    data = json.loads(result.output)
    assert isinstance(data, list)
    assert len(data) >= 1


def test_list_stale_plain() -> None:
    result = runner.invoke(app, ["list", "stale", "--path", str(_STALE_FIXTURE)])
    assert result.exit_code == 0, result.output
    assert len(result.output.strip().splitlines()) >= 1


def test_list_undocumented_no_sources(tmp_path: Path) -> None:
    repo = tmp_path / "r"
    repo.mkdir()
    (repo / "irminsul.toml").write_text(
        'project_name = "r"\n[paths]\ndocs_root = "docs"\nsource_roots = []\n',
        encoding="utf-8",
    )
    (repo / "docs").mkdir()
    result = runner.invoke(app, ["list", "undocumented", "--path", str(repo)])
    assert result.exit_code == 0
    assert "(none)" in result.output


def test_list_lifecycle_queue_uses_required_update_categories() -> None:
    result = runner.invoke(
        app,
        [
            "list",
            "lifecycle",
            "--queue",
            "--format",
            "json",
            "--path",
            str(_LIFECYCLE_FIXTURE),
        ],
    )
    assert result.exit_code == 0, result.output
    data = json.loads(result.output)
    assert any("required update path" in item["reason"] for item in data)
    assert all("follow-up path" not in item["reason"] for item in data)


def test_lifecycle_queue_quotes_suggested_context_path() -> None:
    finding = Finding(
        check="decision-updates",
        category="missing-backlink",
        severity=Severity.warning,
        message="required update doc is missing a backlink",
        path=Path("docs/20-components/doc with spaces.md"),
        doc_id="doc-with-spaces",
    )

    item = _to_queue_item(finding)
    assert item.suggested_command == 'irminsul context "docs/20-components/doc with spaces.md"'
