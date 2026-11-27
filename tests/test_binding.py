"""Tests for binding code names to source with anchors, in any language."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
from typer.testing import CliRunner

from irminsul.anchors import Anchor, parse_anchors, resolve
from irminsul.binding import code_name
from irminsul.checks.claim_anchor import ClaimAnchorCheck
from irminsul.cli import app
from irminsul.config import load
from irminsul.languages import LANGUAGE_REGISTRY, LanguageProfile
from irminsul.source_tree import SourceTree

from .conftest import invoke, invoke_json, run_check, seed_repo, write, write_config, write_doc

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
    assert set(rows) == {"session_cache"}
    [candidate] = rows["session_cache"]["candidates"]
    assert candidate["path"] == "src/session.ts"
    assert candidate["definition"] is True
    assert candidate["marker"] == "<!-- anchor: src/session.ts#session_cache -->"


def test_suggest_reads_no_name_in_the_component_scaffolds_comment(tmp_path: Path) -> None:
    """The comment `irminsul new component` writes shows `Class.method` as an example of a
    code span. A span inside an HTML comment is not a name the doc uses, while one quoting a
    comment marker in prose opens nothing."""
    write_config(tmp_path, source_roots=["src"])
    write(tmp_path, "src/m.py", "def run():\n    return 1\n")
    code, output = invoke(tmp_path, "new", "component", "core")
    assert code == 0, output
    doc = tmp_path / "docs" / "components" / "core.md"
    assert "`Class.method`" in doc.read_text(encoding="utf-8")
    with doc.open("a", encoding="utf-8") as handle:
        handle.write("\nA `<!--` in a span opens nothing, so `walk_tree()` is read.\n")

    report = invoke_json(tmp_path, "anchors", "--suggest", "--doc", "docs/components/core.md")

    assert [row["name"] for row in report["unbound"]] == ["walk_tree"]


def test_an_exported_name_is_resolved_not_unbound(tmp_path: Path) -> None:
    """The exports surface knows `fetchUserSession`, in call form or bare."""
    root = _repo(tmp_path, "Sessions come from `fetchUserSession()` or `fetchUserSession`.")
    result = runner.invoke(app, ["anchors", "--suggest", "--format", "json", "--path", str(root)])
    assert json.loads(result.output)["unbound"] == []


def test_an_anchor_binds_the_name(tmp_path: Path) -> None:
    sentence = "Sessions are kept in `session_cache`."
    unanchored = _repo(tmp_path / "before", sentence)
    result = runner.invoke(
        app, ["anchors", "--suggest", "--format", "json", "--path", str(unanchored)]
    )
    assert [row["name"] for row in json.loads(result.output)["unbound"]] == ["session_cache"]

    root = _repo(
        tmp_path / "after",
        f"{sentence} <!-- anchor: src/session.ts#session_cache -->",
    )
    result = runner.invoke(app, ["anchors", "--suggest", "--format", "json", "--path", str(root)])
    assert json.loads(result.output)["unbound"] == []


def test_the_written_list_names_the_unbound_names_of_a_written_sentence(tmp_path: Path) -> None:
    root = _repo(tmp_path, "Nothing yet.")
    seed_repo(root, "i")
    doc = root / "docs" / "components" / "auth.md"
    doc.write_text(
        doc.read_text(encoding="utf-8") + "\nSessions are kept in `session_cache`.\n",
        encoding="utf-8",
    )

    result = runner.invoke(
        app, ["list", "review", "--written", "--format", "json", "--path", str(root)]
    )

    assert result.exit_code == 0, result.output
    [item] = json.loads(result.output)["items"]
    assert item["unbound"] == ["session_cache"]
    assert "unbound-name" in item["markers"]


def test_the_unbound_advice_is_one_text_shared_by_the_name_line_and_the_legend(
    tmp_path: Path,
) -> None:
    from irminsul.listing.review import UNBOUND_ADVICE

    root = _repo(tmp_path, "Nothing yet.")
    seed_repo(root, "i")
    doc = root / "docs" / "components" / "auth.md"
    doc.write_text(
        doc.read_text(encoding="utf-8") + "\nSessions are kept in `session_cache`.\n",
        encoding="utf-8",
    )

    result = runner.invoke(app, ["list", "review", "--written", "--path", str(root)])

    assert result.exit_code == 0, result.output
    name_line = next(
        line for line in result.output.splitlines() if line.lstrip().startswith("`session_cache`")
    )
    legend_line = next(
        line for line in result.output.splitlines() if line.startswith("  unbound-name")
    )
    assert name_line.endswith(f"unbound; {UNBOUND_ADVICE}")
    assert UNBOUND_ADVICE in legend_line


GO = """\
package env

// Getenv retrieves the variable.
func Getenv(key string) string {
	return lookup(key)
}
"""


def test_a_go_anchor_hashes_the_function_not_its_doc_comment(tmp_path: Path) -> None:
    (tmp_path / "env.go").write_text(GO, encoding="utf-8")
    anchor = Anchor(line=0, raw="", path="env.go", symbol="Getenv", pinned=None)
    before = resolve(tmp_path, anchor).current
    (tmp_path / "env.go").write_text(GO.replace("retrieves", "reads"), encoding="utf-8")
    assert resolve(tmp_path, anchor).current == before
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


def test_a_file_name_of_any_registered_language_is_not_a_code_name(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A language's suffixes are its profile's one list, so a file of a language registered
    a moment ago is known for a file with nothing here edited, as `ledger.mts` is."""
    assert code_name("desk.gox") == "desk.gox"
    monkeypatch.setitem(
        LANGUAGE_REGISTRY,
        "gox",
        LanguageProfile(
            name="gox", source_root_candidates=(), schema_leak_patterns=(), suffixes=(".gox",)
        ),
    )

    suffixes = {suffix for profile in LANGUAGE_REGISTRY.values() for suffix in profile.suffixes}

    assert {".gox", ".py", ".mts", ".cts", ".go", ".rs"} <= suffixes
    assert [suffix for suffix in sorted(suffixes) if code_name(f"ledger{suffix}")] == []


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
    root = _repo(tmp_path, f"{_BUILTIN_SENTENCE} See `session_cache`.")

    assert _unbound_names(root) == ["session_cache"]


def test_the_review_queue_does_not_flag_a_language_builtin_as_unbound(tmp_path: Path) -> None:
    root = _repo(tmp_path, "Nothing yet.")
    seed_repo(root, "i")
    doc = root / "docs" / "components" / "auth.md"
    doc.write_text(doc.read_text(encoding="utf-8") + f"\n{_BUILTIN_SENTENCE}\n", encoding="utf-8")

    result = runner.invoke(
        app, ["list", "review", "--written", "--format", "json", "--path", str(root)]
    )

    [item] = json.loads(result.output)["items"]
    assert item["unbound"] == []
    assert "unbound-name" not in item["markers"]


def test_the_builtins_are_those_of_the_enabled_languages(tmp_path: Path) -> None:
    root = _repo(tmp_path, _BUILTIN_SENTENCE)
    write_config(root, source_roots=["src"], extra='[languages]\nenabled = ["typescript"]\n')

    assert _unbound_names(root) == ["IndexError", "dict.get", "len"]


POLICY = '''\
"""Loan rules."""


def due_day(start_day: int, days: int = 14) -> int:
    return start_day + days


def late_fee(days_late: int) -> int:
    return min(max(days_late, 0) * 25, 500)
'''

LOAN_TESTS = """\
from loans.policy import late_fee


def test_fee_is_capped() -> None:
    assert late_fee(100) == 500
"""

FEE_MARKER = "<!-- anchor: tests/test_loans.py#test_fee_is_capped -->"
GUIDE = "docs/guides/lending.md"


def _lending_repo(
    root: Path,
    files: dict[str, str],
    *,
    guide: str = "The fine `late_fee()` charges stops growing at 5 dollars.",
    test_roots: bool = True,
) -> Path:
    """A guide whose body starts on line 10 and names code of `src/loans/policy.py`, with
    `files` written beside them and `tests` declared as the test root."""
    extra = 'test_roots = ["tests"]\n' if test_roots else ""
    write_config(root, source_roots=["src"], extra=extra)
    write(root, "src/loans/policy.py", POLICY)
    write_doc(root, GUIDE, doc_id="lending", body=f"{guide}\n")
    for rel, text in files.items():
        write(root, rel, text)
    return root


def _resolved(root: Path) -> dict[str, dict[str, Any]]:
    """The `resolved` rows `anchors --suggest --doc` gives for the guide, by name."""
    report = invoke_json(root, "anchors", "--suggest", "--doc", GUIDE)
    return {row["name"]: row for row in report["resolved"]}


def test_suggest_offers_the_test_that_calls_a_function_the_doc_names(tmp_path: Path) -> None:
    root = _lending_repo(tmp_path, {"tests/test_loans.py": LOAN_TESTS})

    code, plain = invoke(root, "anchors", "--suggest", "--doc", GUIDE)

    assert code == 0, plain
    assert plain.splitlines() == [
        f"{GUIDE}:10 `late_fee`, defined at src/loans/policy.py:8",
        f"  tests/test_loans.py:4 (test)  {FEE_MARKER}",
        "0 unbound code name(s), 1 function or class name(s), 1 named by a test",
    ]
    assert invoke_json(root, "anchors", "--suggest", "--doc", GUIDE) == {
        "version": 1,
        "unbound": [],
        "resolved": [
            {
                "path": GUIDE,
                "line": 10,
                "name": "late_fee",
                "definition": {"path": "src/loans/policy.py", "line": 8},
                "tests": [
                    {
                        "path": "tests/test_loans.py",
                        "line": 4,
                        "symbol": "test_fee_is_capped",
                        "marker": FEE_MARKER,
                    }
                ],
            }
        ],
    }


def test_the_marker_suggest_offers_for_a_test_resolves(tmp_path: Path) -> None:
    """A test in a class is offered under the dotted path an anchor accepts, and one inside
    a function, which no anchor reaches, is not offered."""
    root = _lending_repo(
        tmp_path,
        {
            "tests/test_loans.py": "from loans.policy import late_fee\n\n\n"
            "class TestFees:\n"
            "    def test_cap(self) -> None:\n"
            "        assert late_fee(100) == 500\n\n\n"
            "def build():\n"
            "    def test_inner() -> None:\n"
            "        assert late_fee(1) == 25\n\n"
            "    return test_inner\n"
        },
    )

    [offered] = _resolved(root)["late_fee"]["tests"]

    assert offered["marker"] == "<!-- anchor: tests/test_loans.py#TestFees.test_cap -->"
    [anchor] = parse_anchors(offered["marker"])
    assert resolve(root, anchor).status == "ok"


def test_suggest_says_so_when_no_test_names_the_definition(tmp_path: Path) -> None:
    """Three near misses, none a test function that names `late_fee`: a test that imports
    the module and names another of its functions, a function that names it and is no test,
    and a test that names it in a file that does not import its module."""
    root = _lending_repo(
        tmp_path,
        {
            "tests/test_loans.py": "from loans.policy import due_day, late_fee\n\n\n"
            "def test_a_loan_runs_two_weeks() -> None:\n"
            "    assert due_day(0) == 14\n\n\n"
            "def fee_of_a_week() -> int:\n"
            "    return late_fee(7)\n",
            "tests/test_other.py": "def test_a_name_alone(late_fee) -> None:\n"
            "    assert late_fee(100) == 500\n",
        },
    )

    code, plain = invoke(root, "anchors", "--suggest", "--doc", GUIDE)

    assert code == 0, plain
    assert plain.splitlines() == [
        f"{GUIDE}:10 `late_fee`, defined at src/loans/policy.py:8",
        "  no test names it",
        "0 unbound code name(s), 1 function or class name(s), 0 named by a test",
    ]
    assert _resolved(root)["late_fee"]["tests"] == []


def test_suggest_without_a_doc_lists_unbound_names_and_no_test(tmp_path: Path) -> None:
    root = _lending_repo(
        tmp_path,
        {"tests/test_loans.py": LOAN_TESTS, "src/loans/desk.php": "function renewLoan() {}\n"},
        guide="The fine `late_fee()` charges is capped, and `renewLoan()` renews a loan.",
    )
    unbound = [
        f"{GUIDE}:10 `renewLoan`",
        "  src/loans/desk.php:1 (definition)  <!-- anchor: src/loans/desk.php#renewLoan -->",
    ]

    code, plain = invoke(root, "anchors", "--suggest")

    assert code == 0, plain
    assert plain.splitlines() == [*unbound, "1 unbound code name(s)"]
    report = invoke_json(root, "anchors", "--suggest")
    assert set(report) == {"version", "unbound"}
    assert [row["name"] for row in report["unbound"]] == ["renewLoan"]

    with_doc = invoke(root, "anchors", "--suggest", "--doc", GUIDE)[1]
    assert with_doc.splitlines() == [
        *unbound,
        f"{GUIDE}:10 `late_fee`, defined at src/loans/policy.py:8",
        f"  tests/test_loans.py:4 (test)  {FEE_MARKER}",
        "1 unbound code name(s), 1 function or class name(s), 1 named by a test",
    ]


def test_suggest_offers_at_most_three_tests_by_path_and_line(tmp_path: Path) -> None:
    """Five tests name `late_fee`. The three offered are the first by path and then by line,
    which neither the order of their lines alone nor its reverse gives: the one on the
    lowest line, in `tests/test_d.py`, is not offered."""

    def naming(*names: str, padding: int = 0) -> str:
        functions = "".join(
            f"\n\ndef {name}() -> None:\n    assert policy.late_fee(100) == 500\n" for name in names
        )
        return "from loans import policy\n" + "\n" * padding + functions

    root = _lending_repo(
        tmp_path,
        {
            "tests/test_d.py": naming("test_lowest_line_never_offered"),
            "tests/test_b.py": naming("test_third", "test_after_the_third", padding=6),
            "tests/test_a.py": naming("test_first", "test_second", padding=3),
        },
    )

    tests = _resolved(root)["late_fee"]["tests"]

    assert [(test["path"], test["line"], test["symbol"]) for test in tests] == [
        ("tests/test_a.py", 7, "test_first"),
        ("tests/test_a.py", 11, "test_second"),
        ("tests/test_b.py", 10, "test_third"),
    ]


def test_suggest_skips_a_test_file_that_does_not_parse(tmp_path: Path) -> None:
    root = _lending_repo(
        tmp_path,
        {
            "tests/test_broken.py": LOAN_TESTS + "\n\ndef test_unfinished(:\n",
            "tests/test_loans.py": LOAN_TESTS,
        },
    )

    assert [test["path"] for test in _resolved(root)["late_fee"]["tests"]] == [
        "tests/test_loans.py"
    ]


def test_suggest_lists_a_definition_once_and_only_a_span_that_resolves_to_one(
    tmp_path: Path,
) -> None:
    """A second span naming the same function adds no row, a name two functions share
    resolves to neither, and a line of a fenced block is an example, not a code span."""
    root = _lending_repo(
        tmp_path,
        {
            "tests/test_loans.py": LOAN_TESTS,
            "src/loans/desk.py": "def renew():\n    return 1\n",
            "src/loans/shelf.py": "def renew():\n    return 2\n",
        },
        guide="`late_fee()` caps the fine, and `renew()` renews.\n\n"
        "`policy.late_fee` is the same function.\n\n```\ndue_day\n```",
    )

    assert list(_resolved(root)) == ["late_fee"]


def test_suggest_says_when_no_test_root_is_declared(tmp_path: Path) -> None:
    root = _lending_repo(tmp_path, {"tests/test_loans.py": LOAN_TESTS}, test_roots=False)

    plain = invoke(root, "anchors", "--suggest", "--doc", GUIDE)[1]

    assert plain.splitlines()[1:] == [
        "  no test names it",
        "no test file was read: `paths.test_roots` declares no test root",
        "0 unbound code name(s), 1 function or class name(s), 0 named by a test",
    ]


ROOMS = """\
class Desk:
    def run(self) -> int:
        return 1


class Shelf:
    def run(self) -> int:
        return 2
"""
ROOMS_GUIDE = "`Desk.run` opens the desk, and `Shelf.run` opens the shelf."


def _rooms_repo(root: Path, tests: str) -> Path:
    """The lending repository, with two classes of one file that each define `run`, named
    by the guide, and `tests` as `tests/test_rooms.py`."""
    return _lending_repo(
        root,
        {"src/loans/rooms.py": ROOMS, "tests/test_rooms.py": tests},
        guide=ROOMS_GUIDE,
    )


def test_suggest_lists_two_methods_of_one_name_in_one_file(tmp_path: Path) -> None:
    root = _rooms_repo(
        tmp_path,
        "from loans import rooms\n\n\n"
        "def test_both_run() -> None:\n"
        "    assert rooms.Desk().run() + rooms.Shelf().run() == 3\n",
    )
    marker = "<!-- anchor: tests/test_rooms.py#test_both_run -->"

    code, plain = invoke(root, "anchors", "--suggest", "--doc", GUIDE)

    assert code == 0, plain
    assert plain.splitlines() == [
        f"{GUIDE}:10 `Desk.run`, defined at src/loans/rooms.py:2",
        f"  tests/test_rooms.py:4 (test)  {marker}",
        f"{GUIDE}:10 `Shelf.run`, defined at src/loans/rooms.py:7",
        f"  tests/test_rooms.py:4 (test)  {marker}",
        "0 unbound code name(s), 2 function or class name(s), 2 named by a test",
    ]
    report = invoke_json(root, "anchors", "--suggest", "--doc", GUIDE)
    assert [(row["name"], row["definition"]) for row in report["resolved"]] == [
        ("Desk.run", {"path": "src/loans/rooms.py", "line": 2}),
        ("Shelf.run", {"path": "src/loans/rooms.py", "line": 7}),
    ]


def test_a_method_is_named_by_a_test_whose_file_imports_its_class(tmp_path: Path) -> None:
    """A test that imports `Shelf` and reads `.run` names `Shelf.run`, and not `Desk.run`,
    whose class its file does not import."""
    root = _rooms_repo(
        tmp_path,
        "from loans.rooms import Shelf\n\n\n"
        "def test_the_shelf_runs() -> None:\n"
        "    assert Shelf().run() == 2\n",
    )

    resolved = _resolved(root)

    assert resolved["Desk.run"]["tests"] == []
    assert [test["symbol"] for test in resolved["Shelf.run"]["tests"]] == ["test_the_shelf_runs"]


#: Test files that import `loans.policy` and refer to `late_fee` through that import.
NAMING_FILES = {
    "a name imported from the module": "from loans.policy import late_fee\n\n\n"
    "def test_it() -> None:\n    assert late_fee(100) == 500\n",
    "an alias": "from loans.policy import late_fee as fee\n\n\n"
    "def test_it() -> None:\n    assert fee(100) == 500\n",
    "every name of the module": "from loans.policy import *\n\n\n"
    "def test_it() -> None:\n    assert late_fee(100) == 500\n",
    "an attribute of the module imported from its package": "from loans import policy\n\n\n"
    "def test_it() -> None:\n    assert policy.late_fee(100) == 500\n",
    "an attribute of the module by its dotted name": "import loans.policy\n\n\n"
    "def test_it() -> None:\n    assert loans.policy.late_fee(100) == 500\n",
    "an attribute of the module under an alias": "import loans.policy as rules\n\n\n"
    "def test_it() -> None:\n    assert rules.late_fee(100) == 500\n",
    "an import in the test's own body": "def test_it() -> None:\n"
    "    from loans.policy import late_fee\n\n    assert late_fee(100) == 500\n",
}

#: Test files that import `loans.policy` and whose test spells `late_fee` without
#: referring to the function: each of its own bindings is a value of the test's.
SPELLING_FILES = {
    "a parameter or fixture": "from loans.policy import late_fee\n\n\n"
    "def test_it(late_fee: int) -> None:\n    assert late_fee == 3\n",
    "a local variable": "from loans.policy import due_day, late_fee\n\n\n"
    "def test_it() -> None:\n    late_fee = due_day(0)\n    assert late_fee == 14\n",
    "a loop variable": "from loans.policy import due_day, late_fee\n\n\n"
    "def test_it() -> None:\n    for late_fee in (1, 2):\n"
    "        assert due_day(late_fee) > late_fee\n",
    "an attribute of another object": "from loans.policy import due_day\n\n\n"
    "def test_it(record: object) -> None:\n"
    "    assert due_day(record.late_fee) > 0\n",
    "a name imported from another module": "from fees import late_fee\n"
    "from loans.policy import due_day\n\n\n"
    "def test_it() -> None:\n    assert late_fee(due_day(0)) > 0\n",
    "a name its own body imports from another module": "from loans.policy import late_fee\n\n\n"
    "def test_it() -> None:\n    from fees import late_fee\n\n"
    "    assert late_fee(100) == 500\n",
    "the module's name rebound by a parameter": "from loans import policy\n\n\n"
    "def test_it(policy: object) -> None:\n    assert policy.late_fee(100) == 500\n",
    "the rest of a mapping pattern": "from loans.policy import late_fee\n\n\n"
    "def test_it() -> None:\n    match {'a': 1}:\n        case {**late_fee}:\n"
    "            assert late_fee == {'a': 1}\n",
}


@pytest.mark.parametrize("test_file", list(NAMING_FILES.values()), ids=list(NAMING_FILES))
def test_a_test_names_a_definition_through_an_import_of_its_module(
    tmp_path: Path, test_file: str
) -> None:
    root = _lending_repo(tmp_path, {"tests/test_loans.py": test_file})

    assert [test["symbol"] for test in _resolved(root)["late_fee"]["tests"]] == ["test_it"]


@pytest.mark.parametrize("test_file", list(SPELLING_FILES.values()), ids=list(SPELLING_FILES))
def test_a_name_the_test_binds_itself_does_not_name_the_definition(
    tmp_path: Path, test_file: str
) -> None:
    root = _lending_repo(tmp_path, {"tests/test_loans.py": test_file})

    assert _resolved(root)["late_fee"]["tests"] == []


@pytest.mark.xfail(
    strict=True,
    raises=AssertionError,
    reason="BACKLOG.md a-file-level-rebinding-still-names-the-definition",
)
def test_a_name_a_later_import_rebinds_names_what_the_later_import_binds(tmp_path: Path) -> None:
    test_file = (
        "from loans.policy import late_fee as rule\n"
        "from loans.policy import due_day as rule\n\n\n"
        "def test_it() -> None:\n    assert rule(0) == 14\n"
    )
    root = _lending_repo(
        tmp_path,
        {"tests/test_loans.py": test_file},
        guide="The fine `late_fee()` charges is owed from the day `due_day()` gives.",
    )

    resolved = _resolved(root)

    assert resolved["late_fee"]["tests"] == []
    assert [test["symbol"] for test in resolved["due_day"]["tests"]] == ["test_it"]
