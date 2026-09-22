"""Tests for `irminsul status`."""

from __future__ import annotations

import json
from collections.abc import Callable
from pathlib import Path

from typer.testing import CliRunner

from irminsul.cli import app

runner = CliRunner()

FixtureRepo = Callable[[str], Path]


def _status_json(repo: Path) -> dict[str, object]:
    result = runner.invoke(app, ["status", "--format", "json", "--path", str(repo)])
    assert result.exit_code == 0, result.output
    data = json.loads(result.output)
    assert isinstance(data, dict)
    return data


def test_status_json_shape(fixture_repo: FixtureRepo) -> None:
    data = _status_json(fixture_repo("good"))

    assert data["version"] == 1
    assert set(data) == {
        "version",
        "project_name",
        "docs_root",
        "docs",
        "coverage",
        "findings",
    }
    assert data["project_name"] == "good-fixture"
    assert data["docs_root"] == "docs"

    docs = data["docs"]
    assert isinstance(docs, dict)
    assert set(docs) == {"total", "by_layer", "by_status"}
    assert docs["total"] == 2
    assert docs["by_layer"] == {"components": 2}
    assert docs["by_status"] == {"stable": 2}

    coverage = data["coverage"]
    assert isinstance(coverage, dict)
    assert set(coverage) == {
        "source_files",
        "claimed",
        "undocumented",
        "percent",
        "top_undocumented_dirs",
    }

    findings = data["findings"]
    assert isinstance(findings, dict)
    assert set(findings) == {"errors", "warnings", "info", "by_check", "time"}


def test_status_full_coverage(fixture_repo: FixtureRepo) -> None:
    data = _status_json(fixture_repo("good"))
    assert data["coverage"] == {
        "source_files": 1,
        "claimed": 1,
        "undocumented": 0,
        "percent": 100.0,
        "top_undocumented_dirs": [],
    }


def test_status_brownfield_surfaces_invisible_debt(fixture_repo: FixtureRepo) -> None:
    """Unclaimed files are counted even when no directory is doc-covered."""
    repo = fixture_repo("brownfield-status")

    # The covered-dirs heuristic makes this debt invisible to `list undocumented`.
    listed = runner.invoke(app, ["list", "undocumented", "--path", str(repo)])
    assert listed.exit_code == 0, listed.output
    assert "(none)" in listed.output

    data = _status_json(repo)
    assert data["coverage"] == {
        "source_files": 3,
        "claimed": 0,
        "undocumented": 3,
        "percent": 0.0,
        "top_undocumented_dirs": [
            {"path": "app/core", "undocumented": 2},
            {"path": "app/util", "undocumented": 1},
        ],
    }

    findings = data["findings"]
    assert isinstance(findings, dict)
    # The one finding is the orphaned overview doc. Being a draft does not excuse it:
    # an orphan is a statement about the tree around the doc, not about the doc being
    # unfinished, so it is an error whatever its status.
    assert findings["errors"] == 1
    by_check = findings["by_check"]
    assert isinstance(by_check, dict)
    assert by_check.get("orphans") == 1


def test_status_partial_coverage_math(fixture_repo: FixtureRepo) -> None:
    repo = fixture_repo("brownfield-status")
    (repo / "docs" / "components" / "alpha.md").write_text(
        "---\n"
        "id: alpha\n"
        "title: Alpha\n"
        ""
        "status: stable\n"
        "describes:\n"
        "  - app/core/alpha.py\n"
        "tests: []\n"
        "---\n\n# Alpha\n",
        encoding="utf-8",
    )

    data = _status_json(repo)
    coverage = data["coverage"]
    assert isinstance(coverage, dict)
    assert coverage["source_files"] == 3
    assert coverage["claimed"] == 1
    assert coverage["undocumented"] == 2
    assert coverage["percent"] == 33.3
    assert coverage["top_undocumented_dirs"] == [
        {"path": "app/core", "undocumented": 1},
        {"path": "app/util", "undocumented": 1},
    ]


def test_status_plain_smoke(fixture_repo: FixtureRepo) -> None:
    repo = fixture_repo("good")
    result = runner.invoke(app, ["status", "--path", str(repo)])
    assert result.exit_code == 0, result.output
    assert "project: good-fixture (docs/)" in result.output
    assert "docs: 2 total" in result.output
    assert "components: 2" in result.output
    assert "by status: stable 2" in result.output
    assert "coverage: 1/1 source files claimed (100.0%)" in result.output
    assert "findings:" in result.output
    assert all(len(line) <= 80 for line in result.output.splitlines())


def test_status_unknown_format_exits_2(fixture_repo: FixtureRepo) -> None:
    repo = fixture_repo("good")
    result = runner.invoke(app, ["status", "--format", "yaml", "--path", str(repo)])
    assert result.exit_code == 2


def test_status_lists_time_findings(aged_deprecated_repo: Path) -> None:
    data = _status_json(aged_deprecated_repo)
    findings = data["findings"]
    assert isinstance(findings, dict)
    assert [f["code"] for f in findings["time"]] == ["stale-reaper/stale-deprecated-doc"]
    plain = runner.invoke(app, ["status", "--path", str(aged_deprecated_repo)]).output
    assert "time findings: 1" in plain
