"""Tests for `irminsul list orphans/stale/undocumented`."""

from __future__ import annotations

import json
from pathlib import Path

from typer.testing import CliRunner

from irminsul.cli import app

runner = CliRunner()

_ORPHAN_FIXTURE = Path(__file__).parent / "fixtures" / "repos" / "soft-orphans"
_STALE_FIXTURE = Path(__file__).parent / "fixtures" / "repos" / "soft-stale-reaper"


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
