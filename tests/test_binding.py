"""Tests for binding code names to source with anchors, in any language."""

from __future__ import annotations

import json
from pathlib import Path

from typer.testing import CliRunner

from irminsul.anchors import Anchor, parse_anchors, resolve
from irminsul.binding import code_name
from irminsul.checks.claim_anchor import ClaimAnchorCheck
from irminsul.cli import app
from irminsul.config import load
from irminsul.source_tree import SourceTree

from .conftest import run_check, seed_repo, write_config

runner = CliRunner()

TS = """\
export function fetchUserSession(id: string) {
  const session = lookup(id);
  return session;
}

export const SESSION_TTL = 60;

const session_cache = new Map();

function refreshUserSession(id: string) {
  return lookup(id);
}
"""


def _repo(root: Path, body: str) -> Path:
    (root / "src").mkdir(parents=True)
    (root / "src" / "session.ts").write_text(TS, encoding="utf-8")
    write_config(root, source_roots=["src"])
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

    findings = run_check(ClaimAnchorCheck, root)

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
    root = _repo(tmp_path, "Sessions come from `refreshUserSession()` via `session_cache`.")

    result = runner.invoke(app, ["anchors", "--suggest", "--format", "json", "--path", str(root)])

    assert result.exit_code == 0, result.output
    rows = {row["name"]: row for row in json.loads(result.output)["unbound"]}
    assert set(rows) == {"refreshUserSession", "session_cache"}
    [candidate] = rows["refreshUserSession"]["candidates"]
    assert candidate["path"] == "src/session.ts"
    assert candidate["definition"] is True
    assert candidate["marker"] == "<!-- anchor: src/session.ts#refreshUserSession -->"


def test_an_exported_name_is_resolved_not_unbound(tmp_path: Path) -> None:
    """The exports surface knows `fetchUserSession`, in call form or bare."""
    root = _repo(tmp_path, "Sessions come from `fetchUserSession()` or `fetchUserSession`.")
    result = runner.invoke(app, ["anchors", "--suggest", "--format", "json", "--path", str(root)])
    assert json.loads(result.output)["unbound"] == []


def test_an_anchor_binds_the_name(tmp_path: Path) -> None:
    sentence = "Sessions come from `refreshUserSession()`."
    unanchored = _repo(tmp_path / "before", sentence)
    result = runner.invoke(
        app, ["anchors", "--suggest", "--format", "json", "--path", str(unanchored)]
    )
    assert [row["name"] for row in json.loads(result.output)["unbound"]] == ["refreshUserSession"]

    root = _repo(
        tmp_path / "after",
        f"{sentence} <!-- anchor: src/session.ts#refreshUserSession -->",
    )
    result = runner.invoke(app, ["anchors", "--suggest", "--format", "json", "--path", str(root)])
    assert json.loads(result.output)["unbound"] == []


def test_review_lists_unbound_names_on_changed_lines(tmp_path: Path) -> None:
    root = _repo(tmp_path, "Nothing yet.")
    seed_repo(root, "i")
    doc = root / "docs" / "components" / "auth.md"
    doc.write_text(
        doc.read_text(encoding="utf-8") + "\nSessions come from `refreshUserSession()`.\n",
        encoding="utf-8",
    )

    result = runner.invoke(
        app, ["list", "review", "--changed", "--format", "json", "--path", str(root)]
    )

    assert result.exit_code == 0, result.output
    [item] = json.loads(result.output)["items"]
    assert item["unbound"] == ["refreshUserSession"]
    assert "unbound-name" in item["markers"]


def test_the_unbound_advice_is_one_text_shared_by_the_name_line_and_the_legend(
    tmp_path: Path,
) -> None:
    from irminsul.listing.review import UNBOUND_ADVICE

    root = _repo(tmp_path, "Nothing yet.")
    seed_repo(root, "i")
    doc = root / "docs" / "components" / "auth.md"
    doc.write_text(
        doc.read_text(encoding="utf-8") + "\nSessions come from `refreshUserSession()`.\n",
        encoding="utf-8",
    )

    result = runner.invoke(app, ["list", "review", "--changed", "--path", str(root)])

    assert result.exit_code == 0, result.output
    name_line = next(line for line in result.output.splitlines() if "`refreshUserSession`" in line)
    legend_line = next(
        line for line in result.output.splitlines() if line.startswith("  unbound-name")
    )
    assert name_line.endswith(f"unbound; {UNBOUND_ADVICE}")
    assert UNBOUND_ADVICE in legend_line


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
    write_config(tmp_path, source_roots=["src"])
    sources = load_sources(SourceTree(tmp_path, load(tmp_path / "irminsul.toml")))
    [member] = suggest(tmp_path, sources, "field_name").candidates
    assert member.marker("field_name") == "<!-- anchor: src/m.py#A.field_name -->"
    anchor = Anchor(line=0, raw="", path="src/m.py", symbol="A.field_name", pinned=None)
    assert resolve(tmp_path, anchor).status == "ok"
    assert [c.path for c in suggest(tmp_path, sources, "A").candidates] == ["src/m.py"]


NESTED = """\
def create_server(root):
    registry = {}

    def context_changed():
        registry = root
        return registry

    return context_changed
"""


def _nested_repo(root: Path, body: str) -> Path:
    _repo(root, body)
    (root / "src" / "server.py").write_text(NESTED, encoding="utf-8")
    (root / "src" / "template.txt").write_text("Call context_changed first.\n", encoding="utf-8")
    return root


def test_suggest_names_a_definition_no_anchor_can_reach(tmp_path: Path) -> None:
    """A nested definition was reported as "no source file contains it", and a text file
    that only mentioned the name was offered as the place to bind it."""
    root = _nested_repo(tmp_path, "Changes are mapped by `context_changed()`.")

    result = runner.invoke(app, ["anchors", "--suggest", "--format", "json", "--path", str(root)])

    [row] = json.loads(result.output)["unbound"]
    assert row["candidates"] == []
    assert row["unreachable"] == [
        {"path": "src/server.py", "line": 4, "symbol": "create_server.context_changed"}
    ]
    plain = runner.invoke(app, ["anchors", "--suggest", "--path", str(root)]).output
    assert "defines it as `create_server.context_changed`" in plain
    assert "no source file" not in plain


def test_a_local_variable_is_not_a_definition(tmp_path: Path) -> None:
    from irminsul.binding import load_sources, suggest

    root = _nested_repo(tmp_path, "")
    sources = load_sources(SourceTree(root, load(root / "irminsul.toml")))
    found = suggest(root, sources, "registry")
    assert found.unreachable == [] and found.candidates == []


def test_a_mention_is_offered_only_when_nothing_defines_the_name(tmp_path: Path) -> None:
    from irminsul.binding import load_sources, suggest

    root = _nested_repo(tmp_path, "")
    (root / "src" / "notes.txt").write_text("Call `lonely_name` here.\n", encoding="utf-8")
    sources = load_sources(SourceTree(root, load(root / "irminsul.toml")))
    [mention] = suggest(root, sources, "lonely_name").candidates
    assert (mention.path, mention.definition) == ("src/notes.txt", False)


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


def test_a_call_form_span_resolves_to_a_surface_identity(tmp_path: Path) -> None:
    """`context_changed()` matched no surface while `context_changed` matched the MCP tool,
    so the call form was reported unbound."""
    from irminsul.code_references import CodeResolver

    root = _repo(tmp_path, "")
    (root / "src" / "server.py").write_text(
        "def create_server(server):\n"
        "    @server.tool()\n"
        "    def context_changed() -> str:\n"
        "        return ''\n",
        encoding="utf-8",
    )
    resolver = CodeResolver(SourceTree(root, load(root / "irminsul.toml")))
    for span in ("context_changed", "context_changed()"):
        assert [(r.kind, r.identity) for r in resolver.resolve(span)] == [
            ("mcp", "context_changed")
        ]


_BUILTIN_SENTENCE = (
    "Sessions raise `IndexError` when empty, and `dict.get()` and `len()` are not ours."
)


def _unbound_names(root: Path) -> list[str]:
    result = runner.invoke(app, ["anchors", "--suggest", "--format", "json", "--path", str(root)])
    assert result.exit_code == 0, result.output
    return [row["name"] for row in json.loads(result.output)["unbound"]]


def test_a_name_the_language_defines_is_not_unbound(tmp_path: Path) -> None:
    root = _repo(tmp_path, f"{_BUILTIN_SENTENCE} See `refreshUserSession()`.")

    assert _unbound_names(root) == ["refreshUserSession"]


def test_the_review_queue_does_not_flag_a_language_builtin_as_unbound(tmp_path: Path) -> None:
    root = _repo(tmp_path, "Nothing yet.")
    seed_repo(root, "i")
    doc = root / "docs" / "components" / "auth.md"
    doc.write_text(doc.read_text(encoding="utf-8") + f"\n{_BUILTIN_SENTENCE}\n", encoding="utf-8")

    result = runner.invoke(
        app, ["list", "review", "--changed", "--format", "json", "--path", str(root)]
    )

    [item] = json.loads(result.output)["items"]
    assert item["unbound"] == []
    assert "unbound-name" not in item["markers"]


def test_the_builtins_are_those_of_the_enabled_languages(tmp_path: Path) -> None:
    root = _repo(tmp_path, _BUILTIN_SENTENCE)
    write_config(root, source_roots=["src"], extra='[languages]\nenabled = ["typescript"]\n')

    assert _unbound_names(root) == ["IndexError", "dict.get", "len"]
