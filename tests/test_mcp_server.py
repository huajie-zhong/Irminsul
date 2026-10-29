"""Tests for the MCP server module (`irminsul mcp`).

The plain `*_json` functions are exercised directly against fixture repos; the
server wiring test is skipped when the optional `mcp` extra is not installed.
"""

from __future__ import annotations

import asyncio
import json
import os
from collections.abc import Callable
from pathlib import Path

import pytest
from typer.testing import CliRunner

from irminsul import mcp_server
from irminsul.cli import app
from irminsul.config import IrminsulConfig, find_config, load
from irminsul.delta import DeltaError
from irminsul.errors import UserError
from irminsul.git.changes import GitChangesError
from irminsul.listing.review import UnknownDocError

from .conftest import anchor_repo, commit_all, git_init, seed_repo, write, write_config

runner = CliRunner()

_GOOD_FIXTURE = Path(__file__).parent / "fixtures" / "repos" / "good"
_BAD_FRONTMATTER_FIXTURE = Path(__file__).parent / "fixtures" / "repos" / "bad-frontmatter"
_ORPHAN_FIXTURE = Path(__file__).parent / "fixtures" / "repos" / "soft-orphans"

EXPECTED_TOOL_NAMES = {
    "orient",
    "context_for_path",
    "context_for_topic",
    "context_after_edit",
    "refs",
    "check",
    "list_docs",
    "surface",
    "anchors",
    "change_status",
    "change_verify",
}

_CHANGE_FIXTURE = Path(__file__).parent / "fixtures" / "repos" / "soft-change-binding"


def _load_config(repo_root: Path) -> IrminsulConfig:
    return load(find_config(repo_root))


# --- context tools ---


def test_context_for_path_json_returns_owner() -> None:
    out = mcp_server.context_for_path_json(
        _GOOD_FIXTURE, _load_config(_GOOD_FIXTURE), ["app/composer.py", "app/composer.py"]
    )
    data = json.loads(out)
    assert data["mode"] == "path"
    assert len(data["results"]) == 1
    assert data["results"][0]["owner"]["id"] == "composer"
    # The packet runs no checks.
    assert "findings" not in data["results"][0]
    assert "validation" not in data


def test_context_for_topic_json_finds_doc() -> None:
    out = mcp_server.context_for_topic_json(_GOOD_FIXTURE, _load_config(_GOOD_FIXTURE), "composer")
    data = json.loads(out)
    assert data["mode"] == "topic"
    assert {result["owner"]["id"] for result in data["results"]} == {"composer"}


def test_context_after_edit_json_maps_untracked_files_and_validates(
    fixture_repo: Callable[[str], Path],
) -> None:
    repo = fixture_repo("good")
    git_init(repo)
    out = mcp_server.context_after_edit_json(repo, _load_config(repo))
    data = json.loads(out)
    assert data["mode"] == "after-edit"
    owners = {result["owner"]["id"] for result in data["results"]}
    assert "composer" in owners
    assert data["validation"]["repository"]["state"] in {"passed", "failed"}


# --- refs tool ---


def test_refs_json_doc_target() -> None:
    out = mcp_server.refs_json(_GOOD_FIXTURE, _load_config(_GOOD_FIXTURE), "composer")
    data = json.loads(out)
    assert data["target"] == "composer"
    assert set(data) == {"target", "strong", "weak"}


def test_refs_json_reports_a_target_that_names_no_doc() -> None:
    """A mistyped doc id used to fall back to a symbol search and come back as an empty
    result of another shape, which read as a doc nothing references."""
    from irminsul.refs import RefsError

    with pytest.raises(RefsError):
        mcp_server.refs_json(_GOOD_FIXTURE, _load_config(_GOOD_FIXTURE), "composer.py")


# --- check tool ---


def test_check_json_green_repo_has_no_errors(fixture_repo: Callable[[str], Path]) -> None:
    """A copy, unlike its neighbours, because this one asserts a *verdict*.

    The fixture directories live inside this repository, so a run over one in place inherits
    that repository's git state — and `history-depth` reports a shallow clone as a certain
    finding, truthfully, because the checks that read commit history cannot. CI clones the
    test job at depth 1, so "this green fixture has no errors" became a statement about how
    the outer checkout was fetched. The tests that assert a finding *is* reported are
    unaffected and stay in place; this one asks whether anything is wrong, which only the
    fixture should be able to answer.
    """
    repo = fixture_repo("good")
    out = mcp_server.check_json(repo, _load_config(repo))
    data = json.loads(out)
    assert data["summary"]["errors"] == 0


def test_check_json_reports_errors() -> None:
    out = mcp_server.check_json(_BAD_FRONTMATTER_FIXTURE, _load_config(_BAD_FRONTMATTER_FIXTURE))
    data = json.loads(out)
    assert data["summary"]["errors"] > 0
    assert any(f["check"] == "frontmatter" for f in data["findings"])


def test_check_json_runs_the_enabled_checks() -> None:
    out = mcp_server.check_json(_ORPHAN_FIXTURE, _load_config(_ORPHAN_FIXTURE))
    data = json.loads(out)
    assert any(f["check"] == "orphans" for f in data["findings"])


def test_check_json_only_runs_the_named_checks() -> None:
    out = mcp_server.check_json(_ORPHAN_FIXTURE, _load_config(_ORPHAN_FIXTURE), ["links"])
    assert not any(f["check"] == "orphans" for f in json.loads(out)["findings"])


def test_check_json_rejects_an_unknown_check_name() -> None:
    with pytest.raises(ValueError, match="unknown check name"):
        mcp_server.check_json(_GOOD_FIXTURE, _load_config(_GOOD_FIXTURE), ["orphan"])


# --- list_docs tool ---


def test_list_docs_json_all_kinds_return_lists() -> None:
    config = _load_config(_GOOD_FIXTURE)
    for kind in ("undocumented", "lifecycle"):
        data = json.loads(mcp_server.list_docs_json(_GOOD_FIXTURE, config, kind))
        assert isinstance(data, list)


def test_list_docs_json_rejects_unknown_kind_naming_every_kind() -> None:
    with pytest.raises(
        ValueError, match=r"unknown list kind 'everything'; expected one of: .*lifecycle, review$"
    ):
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
    write_config(repo, source_roots=["src"])
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


# --- anchors tool ---


def test_anchors_json_reports_unpinned_anchor(tmp_path: Path) -> None:
    repo = anchor_repo(tmp_path)
    out = mcp_server.anchors_json(repo, _load_config(repo))
    data = json.loads(out)
    assert data["version"] == 1
    assert [f["check"] for f in data["findings"]] == ["claim-anchor"]
    assert data["summary"] == {"errors": 0, "warnings": 0, "info": 1}


# --- change lifecycle tools ---


def test_change_status_json_reports_the_lifecycle_state() -> None:
    out = mcp_server.change_status_json(
        _CHANGE_FIXTURE, _load_config(_CHANGE_FIXTURE), "0001-accepted-good"
    )
    data = json.loads(out)
    assert data["state"] == "accepted"
    assert data["valid_transitions"] == ["implemented", "rejected"]


def test_change_verify_json_reports_blockers() -> None:
    out = mcp_server.change_verify_json(
        _CHANGE_FIXTURE, _load_config(_CHANGE_FIXTURE), "0002-accepted-missing-affects"
    )
    data = json.loads(out)
    assert any(b["code"] == "change-binding/missing-affects" for b in data["blockers"])


@pytest.mark.parametrize("committed_only", [False, True])
def test_the_change_tools_judge_the_same_change_as_the_cli(
    fixture_repo: Callable[[str], Path], committed_only: bool
) -> None:
    repo = fixture_repo("soft-change-binding")
    base = seed_repo(repo, "init")
    login = repo / "app" / "auth" / "login.py"
    login.write_text(login.read_text(encoding="utf-8") + "\n# edited\n", encoding="utf-8")
    config = _load_config(repo)
    tail = ["--base-ref", base, "--format", "json", "--path", str(repo)]
    if committed_only:
        tail.append("--committed-only")

    after_edit = mcp_server.context_after_edit_json(repo, config, base, committed_only)
    cli = runner.invoke(app, ["context", "--after-edit", *tail])
    assert json.loads(after_edit) == json.loads(cli.output)
    assert bool(json.loads(after_edit)["results"]) is not committed_only

    verify = mcp_server.change_verify_json(repo, config, "0001-accepted-good", base, committed_only)
    cli = runner.invoke(app, ["change", "verify", "0001-accepted-good", *tail])
    assert cli.exit_code == 0, cli.output
    assert json.loads(verify) == json.loads(cli.output)


# --- MCPServer wiring ---


def test_mcp_server_registers_expected_tools() -> None:
    pytest.importorskip("mcp")
    import asyncio

    server = mcp_server.create_server(_GOOD_FIXTURE)
    tools = asyncio.run(server.list_tools())
    assert {tool.name for tool in tools} == EXPECTED_TOOL_NAMES


def test_context_for_topic_tool_says_headings_are_searched() -> None:
    pytest.importorskip("mcp")
    import asyncio

    server = mcp_server.create_server(_GOOD_FIXTURE)
    tools = {tool.name: tool for tool in asyncio.run(server.list_tools())}

    assert "headings" in (tools["context_for_topic"].description or "")


def test_context_for_path_tool_says_tests_are_ranked_with_reasons() -> None:
    pytest.importorskip("mcp")
    import asyncio

    server = mcp_server.create_server(_GOOD_FIXTURE)
    tools = {tool.name: tool for tool in asyncio.run(server.list_tools())}

    assert "test_reasons" in (tools["context_for_path"].description or "")


def test_check_tool_sees_a_commit_made_between_calls(tmp_path: Path) -> None:
    """The server lives for a whole editor session, so git history read for one call must
    not answer the next: a commit that makes a doc lag its source has to show up."""
    import datetime as _dt

    root = tmp_path / "r"
    (root / "app").mkdir(parents=True)
    (root / "app" / "thing.py").write_text("X = 1\n", encoding="utf-8")
    (root / "docs" / "components").mkdir(parents=True)
    (root / "docs" / "components" / "thing.md").write_text(
        "---\nid: thing\ntitle: Thing\nstatus: stable\ndescribes:\n  - app/thing.py\n"
        "---\n\n# Thing\n\nThe thing.\n",
        encoding="utf-8",
    )
    write_config(
        root,
        project_name="mcp-git",
        source_roots=["app"],
        enabled=["mtime-drift"],
        extra="[overrides]\nmtime_drift_days = 30\n",
    )
    old = _dt.datetime(2024, 1, 1, tzinfo=_dt.UTC)
    seed_repo(root, "seed", when=old)

    def codes() -> list[str]:
        payload = json.loads(mcp_server.check_json(root, load(find_config(root))))
        return [finding["code"] for finding in payload["findings"]]

    assert codes() == []

    (root / "app" / "thing.py").write_text("X = 2\n", encoding="utf-8")
    commit_all(root, "change the source without the doc")

    assert codes() == ["mtime-drift/drift-detected"]


def test_check_json_audits_ignore_comments(fixture_repo: Callable[[str], Path]) -> None:
    """An ignore comment that suppresses nothing fails `irminsul check`; the tool assembled
    its own run without the audit and reported the repository clean."""
    repo = fixture_repo("good")
    doc = repo / "docs" / "components" / "composer.md"
    doc.write_text(
        doc.read_text(encoding="utf-8")
        + '\n<!-- irminsul:ignore orphans reason="nothing to hide" -->\n',
        encoding="utf-8",
    )

    data = json.loads(mcp_server.check_json(repo, _load_config(repo)))

    assert "ignore-comment/unused" in {f["code"] for f in data["findings"]}
    assert data["summary"]["errors"] > 0


def test_check_json_applies_the_baseline_and_says_so(fixture_repo: Callable[[str], Path]) -> None:
    repo = fixture_repo("bad-frontmatter")
    assert runner.invoke(app, ["baseline", "init", "--path", str(repo)]).exit_code == 0

    data = json.loads(mcp_server.check_json(repo, _load_config(repo)))

    assert data["baseline"]["applied"] is True
    assert data["baseline"]["suppressed"] > 0


def test_check_json_reports_the_adoption_record(fixture_repo: Callable[[str], Path]) -> None:
    """The CLI's report says how much ownership debt a record excepts; the tool left the
    object out, so an agent reading a clean result could not tell it from a tree with none."""
    repo = fixture_repo("brownfield")
    git_init(repo, branch="main")
    commit_all(repo, "seed")
    assert runner.invoke(app, ["adoption", "init", "--path", str(repo)]).exit_code == 0

    data = json.loads(mcp_server.check_json(repo, _load_config(repo)))

    assert data["adoption"]["readable"] is True
    assert data["adoption"]["remaining"] > 0


# --- code changed on disk ---

_TOOL_ARGS: dict[str, dict[str, object]] = {
    "orient": {},
    "context_for_path": {"paths": ["app/composer.py"]},
    "context_for_topic": {"query": "composer"},
    "context_after_edit": {},
    "refs": {"target": "composer"},
    "check": {},
    "list_docs": {"kind": "undocumented"},
    "surface": {"kind": "cli"},
    "anchors": {},
    "change_status": {"change": "anything"},
    "change_verify": {"change": "anything"},
}


def _package(root: Path) -> Path:
    write(root, "__init__.py", "")
    write(root, "cli.py", "A = 1\n")
    write(root, "sub/deep.py", "B = 1\n")
    write(root, "scaffolds/readme.txt", "not code\n")
    return root


def _touch(path: Path) -> None:
    stat = path.stat()
    os.utime(path, ns=(stat.st_atime_ns, stat.st_mtime_ns + 1_000_000_000))


def _resize(path: Path) -> None:
    stat = path.stat()
    path.write_text(path.read_text(encoding="utf-8") + "# more\n", encoding="utf-8")
    os.utime(path, ns=(stat.st_atime_ns, stat.st_mtime_ns))


def test_code_fingerprint_lists_python_files_by_posix_path(tmp_path: Path) -> None:
    package = _package(tmp_path / "pkg")

    fingerprint = mcp_server.code_fingerprint(package)

    assert [path for path, _, _ in fingerprint] == ["__init__.py", "cli.py", "sub/deep.py"]


def test_package_dir_is_the_installed_irminsul_package() -> None:
    paths = {path for path, _, _ in mcp_server.code_fingerprint(mcp_server.PACKAGE_DIR)}

    assert {"__init__.py", "cli.py", "mcp_server.py", "checks/pipeline.py"} <= paths


def test_stale_code_message_is_none_while_nothing_changed(tmp_path: Path) -> None:
    package = _package(tmp_path / "pkg")
    loaded = mcp_server.code_fingerprint(package)

    write(package, "scaffolds/readme.txt", "still not code, and longer\n")

    assert mcp_server.stale_code_message(package, loaded) is None


@pytest.mark.parametrize("change", [_touch, _resize], ids=["mtime", "size"])
def test_stale_code_message_names_a_modified_file(
    tmp_path: Path, change: Callable[[Path], None]
) -> None:
    package = _package(tmp_path / "pkg")
    loaded = mcp_server.code_fingerprint(package)

    change(package / "sub" / "deep.py")

    message = mcp_server.stale_code_message(package, loaded)
    assert message is not None
    assert "sub/deep.py (modified)" in message
    assert "cli.py" not in message


def test_stale_code_message_names_an_added_file(tmp_path: Path) -> None:
    package = _package(tmp_path / "pkg")
    loaded = mcp_server.code_fingerprint(package)

    write(package, "new/feature.py", "C = 1\n")

    message = mcp_server.stale_code_message(package, loaded)
    assert message is not None
    assert "new/feature.py (added)" in message


def test_stale_code_message_names_a_removed_file(tmp_path: Path) -> None:
    package = _package(tmp_path / "pkg")
    loaded = mcp_server.code_fingerprint(package)

    (package / "cli.py").unlink()

    message = mcp_server.stale_code_message(package, loaded)
    assert message is not None
    assert "cli.py (removed)" in message


def test_stale_code_message_names_three_files_and_counts_the_rest(tmp_path: Path) -> None:
    package = tmp_path / "pkg"
    for letter in "abcde":
        write(package, f"{letter}.py", "X = 1\n")
    loaded = mcp_server.code_fingerprint(package)

    for letter in "abcde":
        _touch(package / f"{letter}.py")

    message = mcp_server.stale_code_message(package, loaded)
    assert message is not None
    assert "a.py (modified), b.py (modified), c.py (modified) and 2 more" in message
    assert "d.py" not in message


def test_stale_code_message_says_how_to_recover(tmp_path: Path) -> None:
    package = _package(tmp_path / "pkg")
    loaded = mcp_server.code_fingerprint(package)

    _touch(package / "cli.py")

    message = mcp_server.stale_code_message(package, loaded)
    assert message is not None
    assert "/mcp" in message
    assert "reconnect irminsul" in message
    assert "irminsul orient --format json" in message


def test_server_refuses_every_tool_once_its_code_changed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Python imported the server's code once, so after an upgrade it would answer from the
    old modules; the agent has to be told rather than served a stale tool set."""
    pytest.importorskip("mcp")
    from mcp.server.mcpserver.exceptions import ToolError

    package = _package(tmp_path / "pkg")
    monkeypatch.setattr(mcp_server, "PACKAGE_DIR", package)
    server = mcp_server.create_server(_GOOD_FIXTURE)
    assert _TOOL_ARGS.keys() == EXPECTED_TOOL_NAMES

    async def call_all() -> None:
        await server.call_tool("orient", {})
        _touch(package / "cli.py")
        for name, args in _TOOL_ARGS.items():
            with pytest.raises(ToolError, match=r"cli\.py \(modified\).*reconnect irminsul"):
                await server.call_tool(name, args)

    asyncio.run(call_all())


# --- errors reach the agent ---


def _call_tool(repo: Path, name: str, args: dict[str, object]) -> object:
    server = mcp_server.create_server(repo)
    return asyncio.run(server.call_tool(name, args))


@pytest.mark.parametrize(
    ("tool", "args", "cli"),
    [
        ("refs", {"target": "nope"}, ["refs", "nope"]),
        ("check", {"only": ["orphan"]}, ["check", "--only", "orphan"]),
        ("surface", {"kind": "zzz"}, ["surface", "zzz"]),
        ("change_status", {"change": "nope"}, ["change", "status", "nope"]),
        ("context_for_path", {"paths": ["missing.py"]}, ["context", "missing.py"]),
    ],
    ids=["refs", "check", "surface", "change", "context"],
)
def test_server_gives_the_agent_the_message_the_cli_prints(
    tool: str, args: dict[str, object], cli: list[str]
) -> None:
    """The SDK withholds the text of a plain exception, which left the agent with "Error
    executing tool refs" and no way to learn that its target named no doc."""
    pytest.importorskip("mcp")
    from mcp.server.mcpserver.exceptions import ToolError, UnexpectedToolError

    result = runner.invoke(app, [*cli, "--path", str(_GOOD_FIXTURE)])
    assert result.exit_code != 0
    message = result.output.strip()
    assert message

    with pytest.raises(ToolError) as caught:
        _call_tool(_GOOD_FIXTURE, tool, args)

    assert not isinstance(caught.value, UnexpectedToolError)
    assert str(caught.value).endswith(message)


def test_server_gives_the_agent_the_unknown_list_kind_message() -> None:
    pytest.importorskip("mcp")
    from mcp.server.mcpserver.exceptions import ToolError

    with pytest.raises(ToolError, match="unknown list kind 'everything'; expected one of"):
        _call_tool(_GOOD_FIXTURE, "list_docs", {"kind": "everything"})


def test_server_gives_the_agent_a_config_error(tmp_path: Path) -> None:
    pytest.importorskip("mcp")
    from mcp.server.mcpserver.exceptions import ToolError

    write(tmp_path, "irminsul.toml", "paths = [\n")

    result = runner.invoke(app, ["orient", "--path", str(tmp_path)])
    assert result.exit_code == 2

    with pytest.raises(ToolError) as caught:
        _call_tool(tmp_path, "orient", {})

    assert "not valid TOML" in str(caught.value)
    assert str(caught.value).endswith(result.output.strip())


@pytest.mark.parametrize(
    "error",
    [UnknownDocError("--doc: no doc"), GitChangesError("git status failed"), DeltaError("no base")],
    ids=lambda error: type(error).__name__,
)
def test_server_turns_any_user_error_into_a_tool_error(
    monkeypatch: pytest.MonkeyPatch, error: UserError
) -> None:
    """The CLI's one handler catches `UserError`, so the server does too; a hand-kept list of
    its subclasses is a list a new subclass is missing from."""
    pytest.importorskip("mcp")
    from mcp.server.mcpserver.exceptions import ToolError, UnexpectedToolError

    def refuse(*_: object) -> str:
        raise error

    monkeypatch.setattr(mcp_server, "orient_json", refuse)

    with pytest.raises(ToolError) as caught:
        _call_tool(_GOOD_FIXTURE, "orient", {})

    assert not isinstance(caught.value, UnexpectedToolError)
    assert str(caught.value).endswith(str(error))


def test_server_keeps_an_unexpected_crash_a_crash(monkeypatch: pytest.MonkeyPatch) -> None:
    pytest.importorskip("mcp")
    from mcp.server.mcpserver.exceptions import UnexpectedToolError

    def boom(*_: object) -> str:
        raise ValueError("internal detail")

    monkeypatch.setattr(mcp_server, "orient_json", boom)

    with pytest.raises(UnexpectedToolError) as caught:
        _call_tool(_GOOD_FIXTURE, "orient", {})

    assert "internal detail" not in str(caught.value)
