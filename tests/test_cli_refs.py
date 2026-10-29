"""Tests for `irminsul refs`."""

from __future__ import annotations

import json
from pathlib import Path

from typer.testing import CliRunner

from irminsul.cli import app

from .conftest import write, write_doc

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
    docs = repo / "docs" / "components"
    docs.mkdir(parents=True)
    (docs / "core.md").write_text(
        "\n".join(
            [
                "---",
                "id: core",
                'title: "Core"',
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
        "strong": [{"doc_id": "core", "path": "docs/components/core.md", "line": 6}],
        "weak": [
            {"doc_id": "core", "path": "docs/components/core.md", "line": 20},
            {"doc_id": "note", "path": "docs/components/note.md", "line": 10},
        ],
    }


def test_refs_doc_path_plain_lists_backlinks(tmp_path: Path) -> None:
    repo = _make_refs_repo(tmp_path)

    result = runner.invoke(
        app,
        ["refs", "docs/components/helper.md", "--path", str(repo)],
    )

    assert result.exit_code == 0, result.output
    assert "target: helper" in result.output
    assert "core docs/components/core.md:6" in result.output
    assert "note docs/components/note.md:10" in result.output


def test_refs_rejects_missing_input(tmp_path: Path) -> None:
    repo = _make_refs_repo(tmp_path)

    result = runner.invoke(app, ["refs", "--path", str(repo)])

    assert result.exit_code == 2
    assert "Missing argument" in result.output


def test_refs_a_check_name_or_finding_code_points_at_explain(tmp_path: Path) -> None:
    repo = _make_refs_repo(tmp_path)

    for target in ("prose-file-reference", "links/broken-link"):
        result = runner.invoke(app, ["refs", target, "--path", str(repo)])

        assert result.exit_code == 2
        assert f"unknown doc target: {target}" in result.output
        assert f"`irminsul explain {target}`" in result.output
        assert "context --topic" not in result.output


def test_refs_any_other_unknown_target_points_at_context_topic(tmp_path: Path) -> None:
    repo = _make_refs_repo(tmp_path)

    result = runner.invoke(app, ["refs", "no-such-doc", "--path", str(repo)])
    spaced = runner.invoke(app, ["refs", "markdown links", "--path", str(repo)])

    assert result.exit_code == 2
    assert "unknown doc target: no-such-doc" in result.output
    assert "`irminsul context --topic no-such-doc`" in result.output
    assert "irminsul explain" not in result.output
    assert spaced.exit_code == 2
    assert '`irminsul context --topic "markdown links"`' in spaced.output


def test_refs_a_guidance_file_target_is_reported_by_its_path(tmp_path: Path) -> None:
    repo = _make_refs_repo(tmp_path)
    write(repo, "docs/AGENTS.md", "Start at [the helper](components/helper.md).\n")
    write_doc(repo, "docs/components/map.md", doc_id="map", body="Read [the map](../AGENTS.md).")

    result = runner.invoke(app, ["refs", "docs/AGENTS.md", "--format", "json", "--path", str(repo)])

    assert result.exit_code == 0, result.output
    data = json.loads(result.output)
    assert data["target"] == "docs/AGENTS.md"
    assert data["strong"] == []
    assert [(hit["doc_id"], hit["path"]) for hit in data["weak"]] == [
        ("map", "docs/components/map.md")
    ]
