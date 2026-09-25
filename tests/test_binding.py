"""Tests for binding code names to source with anchors, in any language."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

from typer.testing import CliRunner

from irminsul.anchors import Anchor, parse_anchors, resolve
from irminsul.binding import code_name
from irminsul.checks.claim_anchor import ClaimAnchorCheck
from irminsul.cli import app
from irminsul.config import load
from irminsul.docgraph import build_graph

runner = CliRunner()

TS = """\
export function fetchUserSession(id: string) {
  const session = lookup(id);
  return session;
}

export const SESSION_TTL = 60;

const session_cache = new Map();
"""


def _repo(root: Path, body: str) -> Path:
    (root / "src").mkdir(parents=True)
    (root / "src" / "session.ts").write_text(TS, encoding="utf-8")
    (root / "irminsul.toml").write_text(
        'project_name = "r"\n[paths]\ndocs_root = "docs"\nsource_roots = ["src"]\n',
        encoding="utf-8",
    )
    doc = root / "docs" / "components" / "auth.md"
    doc.parent.mkdir(parents=True)
    doc.write_text(
        f"---\nid: auth\ntitle: Auth\nstatus: stable\n---\n\n# Auth\n\n{body}\n",
        encoding="utf-8",
    )
    return root


def test_an_anchor_into_typescript_resolves_and_pins_the_block(tmp_path: Path) -> None:
    root = _repo(tmp_path, "")
    anchor = Anchor(1, "", "src/session.ts", "fetchUserSession", None)
    first = resolve(root, anchor)
    assert first.status == "ok"

    source = root / "src" / "session.ts"
    source.write_text(
        TS.replace("export const SESSION_TTL = 60;", "export const SESSION_TTL = 90;")
    )
    assert resolve(root, anchor).current == first.current

    source.write_text(TS.replace("return session;", "return session ?? null;"))
    assert resolve(root, anchor).current != first.current


def test_a_renamed_typescript_symbol_is_a_missing_symbol(tmp_path: Path) -> None:
    root = _repo(tmp_path, "Sessions refresh. <!-- anchor: src/session.ts#fetchUserSession -->")
    source = root / "src" / "session.ts"
    source.write_text(TS.replace("fetchUserSession", "loadSession"), encoding="utf-8")

    findings = ClaimAnchorCheck().run(build_graph(root, load(root / "irminsul.toml")))

    assert [f.code for f in findings] == ["claim-anchor/missing-symbol"]


def test_a_marker_inside_a_code_span_is_an_example() -> None:
    body = "Write `<!-- anchor: path#symbol -->` beside the claim.\n"
    assert parse_anchors(body) == []


def test_code_name_accepts_only_spans_that_cannot_be_words() -> None:
    assert code_name("fetchUserSession()") == "fetchUserSession"
    assert code_name("SESSION_TTL") == "SESSION_TTL"
    assert code_name("store.flush") == "store.flush"
    assert code_name("config.toml") is None
    assert code_name("check") is None
    assert code_name("irminsul check") is None


def test_suggest_lists_unbound_names_with_definition_first(tmp_path: Path) -> None:
    root = _repo(tmp_path, "Sessions come from `fetchUserSession()` via `session_cache`.")

    result = runner.invoke(app, ["anchors", "--suggest", "--format", "json", "--path", str(root)])

    assert result.exit_code == 0, result.output
    rows = {row["name"]: row for row in json.loads(result.output)["unbound"]}
    assert set(rows) == {"fetchUserSession", "session_cache"}
    [candidate] = rows["fetchUserSession"]["candidates"]
    assert candidate["path"] == "src/session.ts"
    assert candidate["definition"] is True
    assert candidate["marker"] == "<!-- anchor: src/session.ts#fetchUserSession -->"


def test_an_anchor_binds_the_name(tmp_path: Path) -> None:
    root = _repo(
        tmp_path,
        "Sessions come from `fetchUserSession()`. <!-- anchor: src/session.ts#fetchUserSession -->",
    )
    result = runner.invoke(app, ["anchors", "--suggest", "--format", "json", "--path", str(root)])
    assert json.loads(result.output)["unbound"] == []


def test_review_lists_unbound_names_on_changed_lines(tmp_path: Path) -> None:
    root = _repo(tmp_path, "Nothing yet.")
    subprocess.run(["git", "-C", str(root), "init", "-q"], check=True)
    subprocess.run(["git", "-C", str(root), "add", "-A"], check=True)
    subprocess.run(
        ["git", "-C", str(root), "-c", "user.name=T", "-c", "user.email=t@e", "commit", "-qm", "i"],
        check=True,
    )
    doc = root / "docs" / "components" / "auth.md"
    doc.write_text(
        doc.read_text(encoding="utf-8") + "\nSessions come from `fetchUserSession()`.\n",
        encoding="utf-8",
    )

    result = runner.invoke(
        app, ["list", "review", "--changed", "--format", "json", "--path", str(root)]
    )

    assert result.exit_code == 0, result.output
    [item] = json.loads(result.output)["items"]
    assert item["unbound"] == ["fetchUserSession"]
    assert "unbound-name" in item["markers"]


GO = """\
// Getenv retrieves the variable.
func Getenv(key string) string
{
    return lookup(key)
}
"""


def test_a_go_anchor_hashes_the_function_not_its_doc_comment(tmp_path: Path) -> None:
    (tmp_path / "env.go").write_text(GO, encoding="utf-8")
    anchor = Anchor(line=0, raw="", path="env.go", symbol="Getenv", pinned=None)
    before = resolve(tmp_path, anchor).current
    (tmp_path / "env.go").write_text(GO.replace("lookup(key)", "other(key)"), encoding="utf-8")
    assert resolve(tmp_path, anchor).current != before


def test_an_anchor_into_a_non_utf8_file_is_unreadable(tmp_path: Path) -> None:
    (tmp_path / "legacy.c").write_bytes(b"int caf\xe9 = 1;\n")
    anchor = Anchor(line=0, raw="", path="legacy.c", symbol="x", pinned=None)
    assert resolve(tmp_path, anchor).status == "unreadable"


def test_stdlib_and_file_names_are_not_code_names() -> None:
    for span in ("os.environ", "json.dumps()", "self.surfaces", "setup.cfg", "Cargo.lock"):
        assert code_name(span) is None
    assert code_name("store.flush") == "store.flush"


def test_suggest_only_offers_markers_that_resolve(tmp_path: Path) -> None:
    from irminsul.binding import load_sources, suggest

    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "m.py").write_text("class A:\n    field_name = 1\n", encoding="utf-8")
    (tmp_path / "irminsul.toml").write_text(
        'project_name = "r"\n[paths]\ndocs_root = "docs"\nsource_roots = ["src"]\n',
        encoding="utf-8",
    )
    sources = load_sources(tmp_path, load(tmp_path / "irminsul.toml"))
    assert suggest(tmp_path, sources, "field_name") == []
    assert [c.path for c in suggest(tmp_path, sources, "A")] == ["src/m.py"]


PY = """\
LIMIT = 60
TIMEOUT: int = 5
FIRST, SECOND = 1, 2


class Cfg:
    RETRIES = 3

    def run(self) -> None:
        return None


def helper() -> int:
    return LIMIT
"""


def _py_module(root: Path) -> Path:
    (root / "src").mkdir(parents=True, exist_ok=True)
    source = root / "src" / "mod.py"
    source.write_text(PY, encoding="utf-8")
    return source


def test_a_python_constant_resolves_and_pins_only_its_own_statement(tmp_path: Path) -> None:
    source = _py_module(tmp_path)
    anchor = Anchor(1, "", "src/mod.py", "LIMIT", None)
    first = resolve(tmp_path, anchor)
    assert first.status == "ok"

    source.write_text(PY.replace("return LIMIT", "return LIMIT + 1"), encoding="utf-8")
    assert resolve(tmp_path, anchor).current == first.current

    source.write_text(PY.replace("LIMIT = 60", "LIMIT = 90"), encoding="utf-8")
    assert resolve(tmp_path, anchor).current != first.current


def test_an_annotated_constant_a_tuple_target_and_a_class_attribute_resolve(
    tmp_path: Path,
) -> None:
    _py_module(tmp_path)
    for symbol in ("TIMEOUT", "FIRST", "SECOND", "Cfg.RETRIES", "Cfg.run", "helper"):
        got = resolve(tmp_path, Anchor(1, "", "src/mod.py", symbol, None))
        assert got.status == "ok", f"{symbol} -> {got.status}"


def test_a_name_no_python_statement_binds_is_still_a_missing_symbol(tmp_path: Path) -> None:
    _py_module(tmp_path)
    for symbol in ("ABSENT", "Cfg.ABSENT", "LIMIT.attr", "helper.inner", "self"):
        got = resolve(tmp_path, Anchor(1, "", "src/mod.py", symbol, None))
        assert got.status == "missing_symbol", f"{symbol} -> {got.status}"
