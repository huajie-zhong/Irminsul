"""Tests for `irminsul orient`."""

from __future__ import annotations

import json
from collections.abc import Callable
from pathlib import Path

from typer.testing import CliRunner

from irminsul.cli import app

from .conftest import write_config

runner = CliRunner()

_GOOD_FIXTURE = Path(__file__).parent / "fixtures" / "repos" / "good"


def _make_orient_repo(tmp_path: Path) -> Path:
    repo = tmp_path / "orient"
    repo.mkdir()
    write_config(repo, project_name="orient-demo", source_roots=["src"])

    docs = repo / "docs"
    components = docs / "components"
    components.mkdir(parents=True)
    (docs / "README.md").write_text("# Docs\n", encoding="utf-8")
    (docs / "GLOSSARY.md").write_text("# Glossary\n", encoding="utf-8")
    (components / "core.md").write_text(
        "\n".join(
            [
                "---",
                "id: core",
                'title: "Core"',
                "status: stable",
                "---",
                "",
                "# Core",
                "",
            ]
        ),
        encoding="utf-8",
    )
    (components / "draft-note.md").write_text(
        "\n".join(
            [
                "---",
                "id: draft-note",
                'title: "Draft Note"',
                "status: draft",
                "---",
                "",
                "# Draft Note",
                "",
            ]
        ),
        encoding="utf-8",
    )
    return repo


def test_orient_plain(tmp_path: Path) -> None:
    repo = _make_orient_repo(tmp_path)
    result = runner.invoke(app, ["orient", "--path", str(repo)])
    assert result.exit_code == 0, result.output
    assert "project: orient-demo" in result.output
    assert "docs root: docs" in result.output
    assert "components" in result.output
    assert "entry docs: docs/README.md, docs/GLOSSARY.md" in result.output
    assert "irminsul context <path...>" in result.output
    assert "irminsul context --after-edit" in result.output
    assert "before editing" in result.output
    assert "irminsul check --format json" in result.output


def test_orient_json(tmp_path: Path) -> None:
    repo = _make_orient_repo(tmp_path)
    result = runner.invoke(app, ["orient", "--format", "json", "--path", str(repo)])
    assert result.exit_code == 0, result.output
    data = json.loads(result.output)

    assert data["version"] == 1
    assert data["project_name"] == "orient-demo"
    assert data["docs_root"] == "docs"
    assert data["layers"] == [{"dir": "components", "doc_count": 2}]
    assert data["doc_totals"] == {"total": 2, "by_status": {"draft": 1, "stable": 1}}
    assert data["entry_docs"] == ["docs/README.md", "docs/GLOSSARY.md"]
    assert "frontmatter" in data["checks"]["enabled"]
    assert data["commands"]
    for hint in data["commands"]:
        assert hint["command"]
        assert hint["when"]


def test_orient_reports_root_router_first(tmp_path: Path) -> None:
    repo = _make_orient_repo(tmp_path)
    (repo / "AGENTS.md").write_text("# AGENTS.md\n", encoding="utf-8")

    result = runner.invoke(app, ["orient", "--format", "json", "--path", str(repo)])

    assert result.exit_code == 0, result.output
    data = json.loads(result.output)
    assert data["entry_docs"] == ["AGENTS.md", "docs/README.md", "docs/GLOSSARY.md"]


def test_orient_reports_root_and_docs_router_separately(tmp_path: Path) -> None:
    repo = _make_orient_repo(tmp_path)
    (repo / "AGENTS.md").write_text("# AGENTS.md\n", encoding="utf-8")
    (repo / "docs" / "AGENTS.md").write_text("# Manifest\n", encoding="utf-8")

    result = runner.invoke(app, ["orient", "--format", "json", "--path", str(repo)])

    assert result.exit_code == 0, result.output
    data = json.loads(result.output)
    assert data["entry_docs"] == [
        "AGENTS.md",
        "docs/AGENTS.md",
        "docs/README.md",
        "docs/GLOSSARY.md",
    ]


def test_orient_omits_root_router_when_absent(tmp_path: Path) -> None:
    repo = _make_orient_repo(tmp_path)
    (repo / "README.md").write_text("# Root readme\n", encoding="utf-8")
    (repo / "CLAUDE.md").write_text("# Harness pointer\n", encoding="utf-8")

    result = runner.invoke(app, ["orient", "--format", "json", "--path", str(repo)])

    assert result.exit_code == 0, result.output
    data = json.loads(result.output)
    assert data["entry_docs"] == ["docs/README.md", "docs/GLOSSARY.md"]


def test_orient_json_against_fixture_repo() -> None:
    result = runner.invoke(app, ["orient", "--format", "json", "--path", str(_GOOD_FIXTURE)])
    assert result.exit_code == 0, result.output
    data = json.loads(result.output)
    assert data["version"] == 1
    assert data["project_name"] == "good-fixture"
    assert data["layers"] == [{"dir": "components", "doc_count": 2}]
    assert data["doc_totals"]["total"] == 2
    assert data["entry_docs"] == []
    assert any(hint["command"] == "irminsul fix" for hint in data["commands"])


def test_orient_lists_time_findings(aged_deprecated_repo: Path) -> None:
    result = runner.invoke(app, ["orient", "--format", "json", "--path", str(aged_deprecated_repo)])
    assert result.exit_code == 0, result.output
    codes = [f["code"] for f in json.loads(result.output)["findings"]["time"]]
    assert codes == ["stale-reaper/stale-deprecated-doc"]
    plain = runner.invoke(app, ["orient", "--path", str(aged_deprecated_repo)]).output
    assert "[stale-reaper/stale-deprecated-doc]" in plain


def _orient_json(repo: Path) -> dict:
    result = runner.invoke(app, ["orient", "--format", "json", "--path", str(repo)])
    assert result.exit_code == 0, result.output
    return json.loads(result.output)


def test_orient_counts_unowned_source_no_check_reports(
    fixture_repo: Callable[[str], Path],
) -> None:
    """No directory holds claimed code, so no finding names these files."""
    repo = fixture_repo("brownfield-uncovered")

    listed = runner.invoke(app, ["list", "undocumented", "--path", str(repo)])
    assert listed.exit_code == 0, listed.output
    assert "(none)" in listed.output

    assert _orient_json(repo)["coverage"] == {
        "source_files": 3,
        "claimed": 0,
        "undocumented": 3,
        "percent": 0.0,
        "top_undocumented_dirs": [
            {"path": "app/core", "undocumented": 2},
            {"path": "app/util", "undocumented": 1},
        ],
    }
    plain = runner.invoke(app, ["orient", "--path", str(repo)]).output
    assert "source coverage: 0/3 files owned by a doc (0.0%)" in plain
    assert "app/core" in plain


def test_orient_coverage_counts_partial_ownership(fixture_repo: Callable[[str], Path]) -> None:
    repo = fixture_repo("brownfield-uncovered")
    (repo / "docs" / "components" / "alpha.md").write_text(
        "---\nid: alpha\ntitle: Alpha\nstatus: stable\ndescribes:\n  - app/core/alpha.py\n"
        "---\n\n# Alpha\n",
        encoding="utf-8",
    )

    coverage = _orient_json(repo)["coverage"]

    assert (coverage["source_files"], coverage["claimed"], coverage["percent"]) == (3, 1, 33.3)
    assert coverage["top_undocumented_dirs"] == [
        {"path": "app/core", "undocumented": 1},
        {"path": "app/util", "undocumented": 1},
    ]


def test_orient_coverage_agrees_with_list_undocumented_all(
    fixture_repo: Callable[[str], Path],
) -> None:
    """`status` counted `__init__.py` and test files that `list undocumented --all` leaves
    out, so the two disagreed about the same tree. Both now read one helper."""
    repo = fixture_repo("brownfield-uncovered")
    (repo / "app" / "core" / "__init__.py").write_text("", encoding="utf-8")

    listed = runner.invoke(
        app, ["list", "undocumented", "--all", "--format", "json", "--path", str(repo)]
    )
    assert listed.exit_code == 0, listed.output

    assert _orient_json(repo)["coverage"]["undocumented"] == len(json.loads(listed.output))
