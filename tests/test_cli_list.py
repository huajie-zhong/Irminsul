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
_BROWNFIELD_FIXTURE = Path(__file__).parent / "fixtures" / "repos" / "brownfield"


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


def test_list_undocumented_default_only_covered_dirs() -> None:
    result = runner.invoke(app, ["list", "undocumented", "--path", str(_BROWNFIELD_FIXTURE)])
    assert result.exit_code == 0, result.output
    assert "app/core/helper.py" in result.output
    # Files outside covered directories are invisible without --all.
    assert "app/planner" not in result.output
    assert "app/util" not in result.output


def test_list_undocumented_all_shows_uncovered_files() -> None:
    result = runner.invoke(
        app, ["list", "undocumented", "--all", "--path", str(_BROWNFIELD_FIXTURE)]
    )
    assert result.exit_code == 0, result.output
    for expected in (
        "app/planner/route.py",
        "app/planner/solver.py",
        "app/planner/cost.py",
        "app/util/strings.py",
        "app/util/num.py",
        "app/core/helper.py",
    ):
        assert expected in result.output
    # Claimed and noise files never appear.
    assert "app/core/composer.py" not in result.output
    assert "__init__.py" not in result.output


def test_list_undocumented_all_groups_by_dir_descending() -> None:
    result = runner.invoke(
        app, ["list", "undocumented", "--all", "--path", str(_BROWNFIELD_FIXTURE)]
    )
    assert result.exit_code == 0, result.output
    lines = result.output.strip().splitlines()
    headers = [line for line in lines if not line.startswith("  ")]
    assert headers == [
        "app/planner (3 undocumented)",
        "app/util (2 undocumented)",
        "app/core (1 undocumented)",
    ]
    # Files are indented under their directory header.
    planner_start = lines.index("app/planner (3 undocumented)")
    assert lines[planner_start + 1 : planner_start + 4] == [
        "  app/planner/cost.py",
        "  app/planner/route.py",
        "  app/planner/solver.py",
    ]


def test_list_undocumented_all_json_shape() -> None:
    result = runner.invoke(
        app,
        ["list", "undocumented", "--all", "--format", "json", "--path", str(_BROWNFIELD_FIXTURE)],
    )
    assert result.exit_code == 0, result.output
    data = json.loads(result.output)
    assert len(data) == 6
    assert all(
        set(entry) == {"check", "severity", "message", "path", "dir", "doc_id"} for entry in data
    )
    first = data[0]
    assert first["check"] == "uniqueness"
    assert first["severity"] == "warning"
    assert first["dir"] == "app/planner"
    assert first["path"].startswith("app/planner/")
    assert {entry["path"] for entry in data} == {
        "app/planner/route.py",
        "app/planner/solver.py",
        "app/planner/cost.py",
        "app/util/strings.py",
        "app/util/num.py",
        "app/core/helper.py",
    }


def test_list_undocumented_all_cold_start(tmp_path: Path) -> None:
    """Zero claims anywhere: default shows nothing, --all shows everything."""
    repo = tmp_path / "r"
    (repo / "docs").mkdir(parents=True)
    (repo / "app").mkdir()
    (repo / "irminsul.toml").write_text(
        'project_name = "r"\n[paths]\ndocs_root = "docs"\nsource_roots = ["app"]\n',
        encoding="utf-8",
    )
    (repo / "app" / "a.py").write_text("A = 1\n", encoding="utf-8")
    (repo / "app" / "b.py").write_text("B = 2\n", encoding="utf-8")

    default = runner.invoke(app, ["list", "undocumented", "--path", str(repo)])
    assert default.exit_code == 0, default.output
    assert "(none)" in default.output

    everything = runner.invoke(app, ["list", "undocumented", "--all", "--path", str(repo)])
    assert everything.exit_code == 0, everything.output
    assert "app (2 undocumented)" in everything.output
    assert "app/a.py" in everything.output
    assert "app/b.py" in everything.output


def test_list_undocumented_all_none(tmp_path: Path) -> None:
    repo = tmp_path / "r"
    (repo / "docs").mkdir(parents=True)
    (repo / "irminsul.toml").write_text(
        'project_name = "r"\n[paths]\ndocs_root = "docs"\nsource_roots = []\n',
        encoding="utf-8",
    )
    result = runner.invoke(app, ["list", "undocumented", "--all", "--path", str(repo)])
    assert result.exit_code == 0, result.output
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
