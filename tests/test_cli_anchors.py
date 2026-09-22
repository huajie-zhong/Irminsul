"""Tests for the `irminsul anchors` report output formats."""

from __future__ import annotations

import json
import os
from pathlib import Path

from typer.testing import CliRunner

from irminsul.cli import app

from .conftest import cli_output

runner = CliRunner()


def _make_anchor_repo(tmp_path: Path) -> Path:
    repo = tmp_path / "anchors"
    (repo / "src").mkdir(parents=True)
    (repo / "irminsul.toml").write_text(
        'project_name = "anchors"\n[paths]\ndocs_root = "docs"\nsource_roots = ["src"]\n',
        encoding="utf-8",
    )
    (repo / "src" / "mod.py").write_text("def alpha():\n    return 1\n", encoding="utf-8")
    doc = repo / "docs" / "components" / "c.md"
    doc.parent.mkdir(parents=True)
    doc.write_text(
        "---\nid: c\ntitle: C\nstatus: stable\n"
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


def _two_doc_repo(tmp_path: Path) -> Path:
    repo = _make_anchor_repo(tmp_path)
    (repo / "src" / "other.py").write_text("def beta():\n    return 1\n", encoding="utf-8")
    (repo / "docs" / "components" / "d.md").write_text(
        "---\nid: d\ntitle: D\nstatus: stable\n"
        "describes: [src/other.py]\n---\n\n# D\n\nBeta does a thing.\n"
        "<!-- anchor: src/other.py#beta @sha256:0000deadbeef -->\n",
        encoding="utf-8",
    )
    doc = repo / "docs" / "components" / "c.md"
    doc.write_text(
        doc.read_text(encoding="utf-8").replace(
            "<!-- anchor: src/mod.py#alpha -->",
            "<!-- anchor: src/mod.py#alpha @sha256:0000deadbeef -->",
        ),
        encoding="utf-8",
    )
    return repo


def _pins(repo: Path) -> dict[str, str]:
    import re

    return {
        name: re.search(
            r"sha256:([0-9a-f]+)", (repo / "docs" / "components" / name).read_text("utf-8")
        ).group(1)
        for name in ("c.md", "d.md")
    }


def test_re_pin_without_a_doc_is_refused(tmp_path: Path) -> None:
    """One command used to stamp every drift signal in the repository."""
    repo = _two_doc_repo(tmp_path)
    before = _pins(repo)

    result = runner.invoke(app, ["anchors", "--re-pin", "--path", str(repo)])

    assert result.exit_code == 2
    assert "--doc" in result.output
    assert _pins(repo) == before


def test_re_pin_writes_only_the_named_doc(tmp_path: Path) -> None:
    repo = _two_doc_repo(tmp_path)
    before = _pins(repo)

    result = runner.invoke(
        app, ["anchors", "--re-pin", "--doc", "docs/components/c.md", "--path", str(repo)]
    )
    assert result.exit_code == 0, result.output

    after = _pins(repo)
    assert after["c.md"] != before["c.md"]
    assert after["d.md"] == before["d.md"], "re-pinned a doc the caller did not name"


def test_re_pin_all_writes_every_doc(tmp_path: Path) -> None:
    repo = _two_doc_repo(tmp_path)
    before = _pins(repo)

    result = runner.invoke(app, ["anchors", "--re-pin", "--all", "--path", str(repo)])
    assert result.exit_code == 0, result.output

    after = _pins(repo)
    assert after["c.md"] != before["c.md"] and after["d.md"] != before["d.md"]


def test_repin_never_leaves_a_doc_truncated(tmp_path: Path, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    """A write that fails mid-sweep leaves the doc exactly as it was, and is reported
    rather than escaping as a traceback."""
    repo = _make_anchor_repo(tmp_path)
    doc = repo / "docs" / "components" / "c.md"
    (repo / "src" / "mod.py").write_text("def alpha():\n    return 2\n", encoding="utf-8")
    before = doc.read_text(encoding="utf-8")

    real_replace = os.replace

    def _boom(src, dst):  # type: ignore[no-untyped-def]
        if str(dst).endswith("c.md"):
            raise OSError("disk full")
        return real_replace(src, dst)

    monkeypatch.setattr(os, "replace", _boom)

    result = runner.invoke(app, ["anchors", "--re-pin", "--all", "--path", str(repo)])

    assert result.exit_code == 2
    assert doc.read_text(encoding="utf-8") == before, "the doc was left damaged"
    assert "could not re-pin" in cli_output(result)
