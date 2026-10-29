"""Tests for the static surface extractors."""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

from irminsul.config import IrminsulConfig, SurfaceRule, SurfaceSettings
from irminsul.inventory import get_extractor
from irminsul.inventory.base import SourceReader
from irminsul.languages import LANGUAGE_REGISTRY, TYPESCRIPT_PROFILE

CLI_SRC = """\
import typer

app = typer.Typer()
sub = typer.Typer(name="sub")
app.add_typer(sub)


@app.command()
def top_one():
    pass


@app.command("explicit-name")
def renamed():
    pass


@sub.command()
def leaf():
    pass
"""

HTTP_SRC = """\
from fastapi import FastAPI

app = FastAPI()
router = APIRouter()


@app.get("/items")
def list_items():
    pass


@router.post("/items/{id}")
def make_item():
    pass
"""

TS_SRC = """\
export function alpha() {}
export const beta = 1;
export class Gamma {}
export type Delta = string;
export { hidden as Visible, plain };
export default function () {}
"""

ENV_PY = "import os\nx = os.environ['A_VAR']\ny = os.getenv('B_VAR')\n"
ENV_TS = "const a = process.env.C_VAR;\nconst b = process.env['D_VAR'];\n"

MCP_SRC = """\
def create_server(repo_root):
    server = MCPServer("x")

    @server.tool()
    def orient() -> str:
        return ""

    @server.tool()
    def context_for_path(path: str) -> str:
        return ""

    def _helper() -> str:
        return ""

    return server
"""


def _files(tmp_path: Path, name: str, content: str) -> list[tuple[Path, str]]:
    p = tmp_path / name
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(content, encoding="utf-8")
    return [(p, name)]


def _identities(extractor, files) -> set[str]:
    return {item.identity for item in extractor.extract(files, SourceReader())}


def test_cli_extractor_resolves_names_and_nesting(tmp_path: Path) -> None:
    cfg = IrminsulConfig()
    ids = _identities(get_extractor("cli", cfg), _files(tmp_path, "cli.py", CLI_SRC))
    # implicit name lowercased + hyphenated; explicit name honored; sub-app nested
    assert ids == {"top-one", "explicit-name", "sub leaf"}


def test_http_extractor_emits_method_path(tmp_path: Path) -> None:
    cfg = IrminsulConfig()
    ids = _identities(get_extractor("http", cfg), _files(tmp_path, "api.py", HTTP_SRC))
    assert ids == {"GET /items", "POST /items/{id}"}


def test_exports_extractor_scans_ts(tmp_path: Path) -> None:
    cfg = IrminsulConfig()
    ids = _identities(get_extractor("exports", cfg), _files(tmp_path, "mod.ts", TS_SRC))
    assert {"alpha", "beta", "Gamma", "Delta", "Visible", "plain", "default"} <= ids


def test_env_vars_extractor_python_and_ts(tmp_path: Path) -> None:
    cfg = IrminsulConfig()
    ext = get_extractor("env-vars", cfg)
    py = _identities(ext, _files(tmp_path, "a.py", ENV_PY))
    ts = _identities(ext, _files(tmp_path, "a.ts", ENV_TS))
    assert py == {"A_VAR", "B_VAR"}
    assert ts == {"C_VAR", "D_VAR"}


def test_surface_rule_extractor_from_config(tmp_path: Path) -> None:
    cfg = IrminsulConfig(
        surface=SurfaceSettings(
            rules=[SurfaceRule(kind="routes", globs=("**/*.txt",), pattern=r"^ROUTE (\S+)")]
        )
    )
    ext = get_extractor("routes", cfg)
    assert ext is not None
    ids = _identities(ext, _files(tmp_path, "r.txt", "ROUTE /a\nROUTE /b\nnoise\n"))
    assert ids == {"/a", "/b"}


_TS_SURFACE_SRC = (
    'import { Command } from "commander";\n'
    'const express = require("express");\n'
    "export const alpha = process.env.ALPHA;\n"
    'program.command("go").option("--fast");\n'
    'app.get("/x", handler);\n'
)


@pytest.mark.parametrize("suffix", TYPESCRIPT_PROFILE.suffixes)
def test_every_extractor_reads_every_suffix_of_the_typescript_profile(
    tmp_path: Path, suffix: str
) -> None:
    """The suffixes are the profile's one list: the exports and env-var extractors and the
    commander and express packs each read every file the profile calls TypeScript."""
    cfg = IrminsulConfig()
    files = _files(tmp_path, f"src/mod{suffix}", _TS_SURFACE_SRC)

    read = {
        kind: _identities(get_extractor(kind, cfg), files)
        for kind in ("exports", "env-vars", "cli", "cli-options", "http")
    }

    assert read == {
        "exports": {"alpha"},
        "env-vars": {"ALPHA"},
        "cli": {"go"},
        "cli-options": {"--fast"},
        "http": {"GET /x"},
    }


@pytest.mark.parametrize("suffix", [".rb", ".txt", ".d"])
def test_a_file_no_profile_lists_is_read_by_no_extractor(tmp_path: Path, suffix: str) -> None:
    assert suffix not in {s for p in LANGUAGE_REGISTRY.values() for s in p.suffixes}
    cfg = IrminsulConfig()
    files = _files(tmp_path, f"src/mod{suffix}", _TS_SURFACE_SRC + ENV_PY + "ENV['RUBY_VAR']\n")

    for kind in ("exports", "env-vars", "cli", "cli-options", "http"):
        assert _identities(get_extractor(kind, cfg), files) == set()


def test_exports_extractor_multiline_named_block(tmp_path: Path) -> None:
    cfg = IrminsulConfig()
    src = "export {\n  one,\n  two as Renamed,\n  three,\n};\n"
    ids = _identities(get_extractor("exports", cfg), _files(tmp_path, "barrel.ts", src))
    assert ids == {"one", "Renamed", "three"}


def test_http_extractor_keyword_path(tmp_path: Path) -> None:
    cfg = IrminsulConfig()
    src = 'from fastapi import FastAPI\n\napp = FastAPI()\n\n\n@app.get(path="/kw")\ndef h():\n    pass\n'
    ids = _identities(get_extractor("http", cfg), _files(tmp_path, "kw.py", src))
    assert ids == {"GET /kw"}


def test_mcp_extractor_finds_tool_functions(tmp_path: Path) -> None:
    cfg = IrminsulConfig()
    ext = get_extractor("mcp", cfg)
    assert ext is not None
    ids = _identities(ext, _files(tmp_path, "mcp_server.py", MCP_SRC))
    # decorated tools only; the undecorated _helper and create_server are excluded
    assert ids == {"orient", "context_for_path"}


def test_unknown_kind_has_no_extractor() -> None:
    assert get_extractor("nope", IrminsulConfig()) is None


CLI_OPTIONS_SRC = """from typing import Annotated

import typer

app = typer.Typer()

RootOpt = Annotated[str, typer.Option("--root", help="Shared by every command.")]


@app.command()
def run(
    root: RootOpt = ".",
    profile: Annotated[str, typer.Option("--profile", "-p")] = "hard",
    confirm: Annotated[bool, typer.Option("--confirm/--no-confirm")] = False,
    dry_run: Annotated[bool, typer.Option()] = False,
    legacy: str = typer.Option("x", "--legacy-flag"),
    short_only: Annotated[bool, typer.Option("-s")] = False,
    plain: str = "not an option",
) -> None:
    pass
"""


def test_cli_options_extractor_collects_long_flags(tmp_path: Path) -> None:
    cfg = IrminsulConfig()
    files = _files(tmp_path, "cli.py", CLI_OPTIONS_SRC)
    assert _identities(get_extractor("cli-options", cfg), files) == {
        "--root",
        "--profile",
        "--confirm",
        "--no-confirm",
        "--dry-run",
        "--legacy-flag",
        "--help",
    }


_NOT_UTF8 = b"x = '\xff\xfe'\n"


@pytest.mark.parametrize(
    ("kind", "name", "source", "expected"),
    [
        ("cli", "cli.py", CLI_SRC, {"top-one", "explicit-name", "sub leaf"}),
        ("http", "api.py", HTTP_SRC, {"GET /items", "POST /items/{id}"}),
        ("mcp", "mcp_server.py", MCP_SRC, {"orient", "context_for_path"}),
        ("exports", "mod.ts", TS_SRC, {"alpha", "beta", "Gamma", "Delta", "default"}),
        ("env-vars", "a.py", ENV_PY, {"A_VAR", "B_VAR"}),
        (
            "cli-options",
            "cli.py",
            CLI_OPTIONS_SRC,
            {"--root", "--profile", "--legacy-flag", "--help"},
        ),
    ],
    ids=["cli", "http", "mcp", "exports", "env-vars", "cli-options"],
)
def test_a_source_file_that_is_not_utf8_is_skipped(
    tmp_path: Path, kind: str, name: str, source: str, expected: set[str]
) -> None:
    cfg = IrminsulConfig()
    files = _files(tmp_path, name, source)
    broken = tmp_path / ("broken" + Path(name).suffix)
    broken.write_bytes(_NOT_UTF8)
    extractor = get_extractor(kind, cfg)
    assert extractor is not None
    ids = _identities(extractor, [*files, (broken, broken.name)])
    assert expected <= ids


def test_a_reader_reads_and_parses_each_file_once(tmp_path: Path) -> None:
    """A reader is a snapshot: what it read first is what every later caller gets."""
    path = tmp_path / "a.py"
    path.write_text("def a() -> None:\n    pass\n", encoding="utf-8")
    reader = SourceReader()

    first = reader.module(path)
    path.write_text("def b() -> None:\n    pass\n", encoding="utf-8")

    assert first is not None
    assert reader.module(path) is first
    assert reader.text(path) == "def a() -> None:\n    pass\n"
    fresh = SourceReader().module(path)
    assert fresh is not None
    assert [n.name for n in fresh.nodes if isinstance(n, ast.FunctionDef)] == ["b"]


def test_a_reader_answers_none_for_what_it_cannot_read_or_parse(tmp_path: Path) -> None:
    broken = tmp_path / "broken.py"
    broken.write_bytes(_NOT_UTF8)
    invalid = tmp_path / "invalid.py"
    invalid.write_text("def (:\n", encoding="utf-8")
    reader = SourceReader()

    assert reader.text(broken) is None
    assert reader.module(broken) is None
    assert reader.text(tmp_path / "missing.py") is None
    assert reader.text(invalid) == "def (:\n"
    assert reader.module(invalid) is None
