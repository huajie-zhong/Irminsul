"""Tests for the `irminsul anchors` report output formats."""

from __future__ import annotations

import json
from pathlib import Path

from typer.testing import CliRunner

from irminsul.cli import app

runner = CliRunner()


def _make_anchor_repo(tmp_path: Path) -> Path:
    repo = tmp_path / "anchors"
    (repo / "src").mkdir(parents=True)
    (repo / "irminsul.toml").write_text(
        'project_name = "anchors"\n[paths]\ndocs_root = "docs"\nsource_roots = ["src"]\n',
        encoding="utf-8",
    )
    (repo / "src" / "mod.py").write_text("def alpha():\n    return 1\n", encoding="utf-8")
    doc = repo / "docs" / "20-components" / "c.md"
    doc.parent.mkdir(parents=True)
    doc.write_text(
        "---\nid: c\ntitle: C\naudience: explanation\ntier: 3\nstatus: stable\n"
        "describes: [src/mod.py]\n---\n\n# C\n\nAlpha does a thing.\n"
        "<!-- anchor: src/mod.py#alpha -->\n",
        encoding="utf-8",
    )
    return repo


def test_anchors_report_plain(tmp_path: Path) -> None:
    repo = _make_anchor_repo(tmp_path)
    result = runner.invoke(app, ["anchors", "--path", str(repo)])
    assert result.exit_code == 0, result.output
    assert "1 anchor finding(s)" in result.output


def test_anchors_report_json(tmp_path: Path) -> None:
    repo = _make_anchor_repo(tmp_path)
    result = runner.invoke(app, ["anchors", "--format", "json", "--path", str(repo)])
    assert result.exit_code == 0, result.output
    data = json.loads(result.output)
    assert data["version"] == 1
    assert len(data["findings"]) == 1
    finding = data["findings"][0]
    assert finding["check"] == "claim-anchor"
    assert finding["severity"] == "info"
    assert data["summary"] == {"errors": 0, "warnings": 0, "info": 1}


def test_anchors_rejects_unknown_format(tmp_path: Path) -> None:
    repo = _make_anchor_repo(tmp_path)
    result = runner.invoke(app, ["anchors", "--format", "yaml", "--path", str(repo)])
    assert result.exit_code == 2
    assert "unknown --format" in result.output
