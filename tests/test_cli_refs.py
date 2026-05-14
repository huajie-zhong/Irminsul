"""Tests for `irminsul refs`."""

from __future__ import annotations

import json
from pathlib import Path

from typer.testing import CliRunner

from irminsul.cli import app

runner = CliRunner()


def _make_refs_repo(tmp_path: Path) -> Path:
    repo = tmp_path / "refs"
    repo.mkdir()
    (repo / "irminsul.toml").write_text(
        "\n".join(
            [
                'project_name = "refs"',
                "[paths]",
                'docs_root = "docs"',
                'source_roots = ["src"]',
                "",
            ]
        ),
        encoding="utf-8",
    )
    docs = repo / "docs" / "20-components"
    docs.mkdir(parents=True)
    (docs / "core.md").write_text(
        "\n".join(
            [
                "---",
                "id: core",
                'title: "Core"',
                "audience: explanation",
                "tier: 3",
                "status: stable",
                "depends_on:",
                "  - helper",
                "describes:",
                "  - src/mylib/core.py",
                "claims:",
                "  - id: imports-helper",
                "    state: implemented",
                "    kind: import",
                "    claim: Core imports helper.",
                "    evidence:",
                "      - src/mylib/core.py::run",
                "---",
                "",
                "# Core",
                "",
                "See [Helper](helper.md).",
                "",
            ]
        ),
        encoding="utf-8",
    )
    (docs / "helper.md").write_text(
        "\n".join(
            [
                "---",
                "id: helper",
                'title: "Helper"',
                "audience: explanation",
                "tier: 3",
                "status: stable",
                "describes:",
                "  - src/mylib/helper.py",
                "---",
                "",
                "# Helper",
                "",
            ]
        ),
        encoding="utf-8",
    )
    (docs / "note.md").write_text(
        "\n".join(
            [
                "---",
                "id: note",
                'title: "Note"',
                "audience: explanation",
                "tier: 3",
                "status: draft",
                "describes: []",
                "---",
                "",
                "# Note",
                "",
                "Another [helper reference](helper.md#helper).",
                "",
            ]
        ),
        encoding="utf-8",
    )
    return repo


def test_refs_doc_json_lists_strong_and_weak_backlinks(tmp_path: Path) -> None:
    repo = _make_refs_repo(tmp_path)

    result = runner.invoke(app, ["refs", "helper", "--format", "json", "--path", str(repo)])

    assert result.exit_code == 0, result.output
    data = json.loads(result.output)
    assert data == {
        "target": "helper",
        "strong": [{"doc_id": "core", "path": "docs/20-components/core.md", "line": 8}],
        "weak": [
            {"doc_id": "core", "path": "docs/20-components/core.md", "line": 22},
            {"doc_id": "note", "path": "docs/20-components/note.md", "line": 12},
        ],
    }


def test_refs_doc_path_plain_lists_backlinks(tmp_path: Path) -> None:
    repo = _make_refs_repo(tmp_path)

    result = runner.invoke(
        app,
        ["refs", "docs/20-components/helper.md", "--path", str(repo)],
    )

    assert result.exit_code == 0, result.output
    assert "target: helper" in result.output
    assert "core docs/20-components/core.md:8" in result.output
    assert "note docs/20-components/note.md:12" in result.output


def test_refs_symbol_json_lists_owners_and_evidence_references(tmp_path: Path) -> None:
    repo = _make_refs_repo(tmp_path)

    result = runner.invoke(
        app,
        ["refs", "--symbol", "core.py", "--format", "json", "--path", str(repo)],
    )

    assert result.exit_code == 0, result.output
    data = json.loads(result.output)
    assert data["symbol"] == "core.py"
    assert data["owners"] == [
        {
            "doc_id": "core",
            "path": "docs/20-components/core.md",
            "line": 10,
            "match": "src/mylib/core.py",
        }
    ]
    assert data["references"] == [
        {
            "doc_id": "core",
            "path": "docs/20-components/core.md",
            "line": 17,
            "match": "src/mylib/core.py::run",
        }
    ]


def test_refs_rejects_missing_input(tmp_path: Path) -> None:
    repo = _make_refs_repo(tmp_path)

    result = runner.invoke(app, ["refs", "--path", str(repo)])

    assert result.exit_code == 2
    assert "choose exactly one input" in result.output
