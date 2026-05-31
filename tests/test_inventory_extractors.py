"""Tests for the static surface extractors (RFC 0020)."""

from __future__ import annotations

from pathlib import Path

from irminsul.config import (
    Checks,
    GenericInventoryRule,
    InventoryDriftSettings,
    IrminsulConfig,
)
from irminsul.inventory import get_extractor

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


def _files(tmp_path: Path, name: str, content: str) -> list[tuple[Path, str]]:
    p = tmp_path / name
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(content, encoding="utf-8")
    return [(p, name)]


def _identities(extractor, files, config) -> set[str]:
    return {item.identity for item in extractor.extract(files, config)}


def test_cli_extractor_resolves_names_and_nesting(tmp_path: Path) -> None:
    cfg = IrminsulConfig()
    ids = _identities(get_extractor("cli", cfg), _files(tmp_path, "cli.py", CLI_SRC), cfg)
    # implicit name lowercased + hyphenated; explicit name honored; sub-app nested
    assert ids == {"top-one", "explicit-name", "sub leaf"}


def test_http_extractor_emits_method_path(tmp_path: Path) -> None:
    cfg = IrminsulConfig()
    ids = _identities(get_extractor("http", cfg), _files(tmp_path, "api.py", HTTP_SRC), cfg)
    assert ids == {"GET /items", "POST /items/{id}"}


def test_exports_extractor_scans_ts(tmp_path: Path) -> None:
    cfg = IrminsulConfig()
    ids = _identities(get_extractor("exports", cfg), _files(tmp_path, "mod.ts", TS_SRC), cfg)
    assert {"alpha", "beta", "Gamma", "Delta", "Visible", "plain", "default"} <= ids


def test_env_vars_extractor_python_and_ts(tmp_path: Path) -> None:
    cfg = IrminsulConfig()
    ext = get_extractor("env-vars", cfg)
    py = _identities(ext, _files(tmp_path, "a.py", ENV_PY), cfg)
    ts = _identities(ext, _files(tmp_path, "a.ts", ENV_TS), cfg)
    assert py == {"A_VAR", "B_VAR"}
    assert ts == {"C_VAR", "D_VAR"}


def test_generic_regex_extractor_from_config(tmp_path: Path) -> None:
    cfg = IrminsulConfig(
        checks=Checks(
            inventory_drift=InventoryDriftSettings(
                generic=[
                    GenericInventoryRule(kind="routes", glob="**/*.txt", pattern=r"^ROUTE (\S+)")
                ]
            )
        )
    )
    ext = get_extractor("routes", cfg)
    assert ext is not None
    ids = _identities(ext, _files(tmp_path, "r.txt", "ROUTE /a\nROUTE /b\nnoise\n"), cfg)
    assert ids == {"/a", "/b"}


def test_unknown_kind_has_no_extractor() -> None:
    assert get_extractor("nope", IrminsulConfig()) is None
