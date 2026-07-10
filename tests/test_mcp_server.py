"""Tests for the MCP server module (`irminsul mcp`).

The plain `*_json` functions are exercised directly against fixture repos; the
FastMCP wiring test is skipped when the optional `mcp` extra is not installed.
"""

from __future__ import annotations

import json
import subprocess
from collections.abc import Callable
from pathlib import Path

import pytest
from typer.testing import CliRunner

from irminsul import mcp_server
from irminsul.cli import app
from irminsul.config import IrminsulConfig, find_config, load

runner = CliRunner()

_GOOD_FIXTURE = Path(__file__).parent / "fixtures" / "repos" / "good"
_BAD_FRONTMATTER_FIXTURE = Path(__file__).parent / "fixtures" / "repos" / "bad-frontmatter"
_ORPHAN_FIXTURE = Path(__file__).parent / "fixtures" / "repos" / "soft-orphans"

EXPECTED_TOOL_NAMES = {
    "orient",
    "context_for_path",
    "context_for_topic",
    "context_changed",
    "refs",
    "check",
    "list_docs",
    "surface",
    "anchors",
}


def _load_config(repo_root: Path) -> IrminsulConfig:
    return load(find_config(repo_root))


# --- context tools ---


def test_context_for_path_json_returns_owner() -> None:
    out = mcp_server.context_for_path_json(
        _GOOD_FIXTURE, _load_config(_GOOD_FIXTURE), "app/composer.py"
    )
    data = json.loads(out)
    assert data["mode"] == "path"
    assert len(data["results"]) == 1
    assert data["results"][0]["owner"]["id"] == "composer"


def test_context_for_topic_json_finds_doc() -> None:
    out = mcp_server.context_for_topic_json(_GOOD_FIXTURE, _load_config(_GOOD_FIXTURE), "composer")
    data = json.loads(out)
    assert data["mode"] == "topic"
    assert {result["owner"]["id"] for result in data["results"]} == {"composer"}


def test_context_changed_json_maps_untracked_files(
    fixture_repo: Callable[[str], Path],
) -> None:
    repo = fixture_repo("good")
    subprocess.run(["git", "init", "-q"], cwd=repo, check=True)
    out = mcp_server.context_changed_json(repo, _load_config(repo))
    data = json.loads(out)
    assert data["mode"] == "changed"
    owners = {result["owner"]["id"] for result in data["results"]}
    assert "composer" in owners


# --- refs tool ---


def test_refs_json_doc_target() -> None:
    out = mcp_server.refs_json(_GOOD_FIXTURE, _load_config(_GOOD_FIXTURE), "composer")
    data = json.loads(out)
    assert data["target"] == "composer"
    assert set(data) == {"target", "strong", "weak"}


def test_refs_json_falls_back_to_symbol() -> None:
    out = mcp_server.refs_json(_GOOD_FIXTURE, _load_config(_GOOD_FIXTURE), "composer.py")
    data = json.loads(out)
    assert data["symbol"] == "composer.py"
    assert {hit["doc_id"] for hit in data["owners"]} == {"composer"}


# --- check tool ---


def test_check_json_green_repo_has_no_errors() -> None:
    out = mcp_server.check_json(_GOOD_FIXTURE, _load_config(_GOOD_FIXTURE), "hard")
    data = json.loads(out)
    assert data["summary"]["errors"] == 0


def test_check_json_reports_hard_errors() -> None:
    out = mcp_server.check_json(
        _BAD_FRONTMATTER_FIXTURE, _load_config(_BAD_FRONTMATTER_FIXTURE), "hard"
    )
    data = json.loads(out)
    assert data["summary"]["errors"] > 0
    assert any(f["check"] == "frontmatter" for f in data["findings"])


def test_check_json_configured_profile_runs() -> None:
    out = mcp_server.check_json(_ORPHAN_FIXTURE, _load_config(_ORPHAN_FIXTURE), "configured")
    data = json.loads(out)
    assert any(f["check"] == "orphans" for f in data["findings"])


@pytest.mark.parametrize("profile", ["advisory", "all-available", "bogus"])
def test_check_json_rejects_non_deterministic_profiles(profile: str) -> None:
    with pytest.raises(ValueError, match="unknown check profile"):
        mcp_server.check_json(_GOOD_FIXTURE, _load_config(_GOOD_FIXTURE), profile)


# --- list_docs tool ---


def test_list_docs_json_orphans() -> None:
    out = mcp_server.list_docs_json(_ORPHAN_FIXTURE, _load_config(_ORPHAN_FIXTURE), "orphans")
    data = json.loads(out)
    assert isinstance(data, list)
    assert len(data) >= 1
    assert all(f["check"] == "orphans" for f in data)


def test_list_docs_json_all_kinds_return_lists() -> None:
    config = _load_config(_GOOD_FIXTURE)
    for kind in ("orphans", "stale", "undocumented", "lifecycle"):
        data = json.loads(mcp_server.list_docs_json(_GOOD_FIXTURE, config, kind))
        assert isinstance(data, list)


def test_list_docs_json_rejects_unknown_kind() -> None:
    with pytest.raises(ValueError, match="unknown list kind"):
        mcp_server.list_docs_json(_GOOD_FIXTURE, _load_config(_GOOD_FIXTURE), "everything")


# --- surface tool ---

_CLI_SRC = """\
import typer

app = typer.Typer()


@app.command()
def alpha():
    pass


@app.command()
def beta():
    pass
"""


def _surface_repo(tmp_path: Path) -> Path:
    repo = tmp_path / "r"
    (repo / "src").mkdir(parents=True)
    (repo / "irminsul.toml").write_text(
        'project_name = "r"\n[paths]\ndocs_root = "docs"\nsource_roots = ["src"]\n',
        encoding="utf-8",
    )
    (repo / "src" / "cli.py").write_text(_CLI_SRC, encoding="utf-8")
    return repo


def test_surface_json_lists_identities(tmp_path: Path) -> None:
    repo = _surface_repo(tmp_path)
    out = mcp_server.surface_json(repo, _load_config(repo), "cli")
    data = json.loads(out)
    assert {row["identity"] for row in data} == {"alpha", "beta"}


def test_surface_json_respects_source_glob(tmp_path: Path) -> None:
    repo = _surface_repo(tmp_path)
    out = mcp_server.surface_json(repo, _load_config(repo), "cli", "src/other.py")
    assert json.loads(out) == []


def test_surface_json_rejects_unknown_kind(tmp_path: Path) -> None:
    repo = _surface_repo(tmp_path)
    with pytest.raises(ValueError, match="no extractor for kind"):
        mcp_server.surface_json(repo, _load_config(repo), "bogus")


# --- CLI command ---


def test_cli_mcp_without_dependency_exits_with_install_hint(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import importlib.util

    real_find_spec = importlib.util.find_spec

    def fake_find_spec(name: str, *args: object, **kwargs: object) -> object:
        if name == "mcp":
            return None
        return real_find_spec(name, *args, **kwargs)  # type: ignore[arg-type]

    monkeypatch.setattr(importlib.util, "find_spec", fake_find_spec)
    result = runner.invoke(app, ["mcp", "--path", str(_GOOD_FIXTURE)])
    assert result.exit_code == 1
    try:
        stderr = result.stderr
    except ValueError:
        stderr = ""
    assert "irminsul[mcp]" in result.output + stderr


# --- orient tool ---


def test_orient_json_reports_layout_and_commands() -> None:
    out = mcp_server.orient_json(_GOOD_FIXTURE, _load_config(_GOOD_FIXTURE))
    data = json.loads(out)
    assert data["version"] == 1
    assert data["doc_totals"]["total"] > 0
    assert any(hint["command"].startswith("irminsul context") for hint in data["commands"])


def test_orient_json_matches_cli_output() -> None:
    out = mcp_server.orient_json(_GOOD_FIXTURE, _load_config(_GOOD_FIXTURE))
    result = runner.invoke(app, ["orient", "--format", "json", "--path", str(_GOOD_FIXTURE)])
    assert result.exit_code == 0, result.output
    assert json.loads(out) == json.loads(result.output)


# --- anchors tool ---


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


def test_anchors_json_reports_unpinned_anchor(tmp_path: Path) -> None:
    repo = _make_anchor_repo(tmp_path)
    out = mcp_server.anchors_json(repo, _load_config(repo))
    data = json.loads(out)
    assert data["version"] == 1
    assert [f["check"] for f in data["findings"]] == ["claim-anchor"]
    assert data["summary"] == {"errors": 0, "warnings": 0, "info": 1}


def test_anchors_json_matches_cli_output(tmp_path: Path) -> None:
    repo = _make_anchor_repo(tmp_path)
    out = mcp_server.anchors_json(repo, _load_config(repo))
    result = runner.invoke(app, ["anchors", "--format", "json", "--path", str(repo)])
    assert result.exit_code == 0, result.output
    assert json.loads(out) == json.loads(result.output)


# --- FastMCP wiring ---


def test_fastmcp_server_registers_expected_tools() -> None:
    pytest.importorskip("mcp")
    import asyncio

    server = mcp_server.create_server(_GOOD_FIXTURE)
    tools = asyncio.run(server.list_tools())
    assert {tool.name for tool in tools} == EXPECTED_TOOL_NAMES
