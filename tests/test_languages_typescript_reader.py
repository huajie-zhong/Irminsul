"""TypeScript's reader answers the language interface from its grammar and query file, on a
lending-ledger fixture and on inline samples where a case does not belong in a codebase."""

from __future__ import annotations

import datetime as _dt
from collections.abc import Callable
from pathlib import Path

import pytest

from irminsul.anchors import Anchor, resolve
from irminsul.checks.claim_anchor import ClaimAnchorCheck
from irminsul.code_references import CodeResolver, Reference
from irminsul.config import load
from irminsul.languages import reader_for
from irminsul.languages.reader import CodeReader, CodeReading, Definition
from irminsul.source_tree import SourceTree

from .conftest import (
    FIXTURE_REPOS_DIR,
    commit_all,
    git_init,
    invoke,
    invoke_json,
    replace_text,
    run_check,
    seed_repo,
    write,
    write_doc,
)

SEEDED = _dt.datetime(2024, 1, 1, 12, tzinfo=_dt.UTC)
ROOT = FIXTURE_REPOS_DIR / "typescript-ledger"
PINS = "docs/guides/pins.md"


def _reader(name: str) -> CodeReader:
    reader = reader_for(name)
    assert reader is not None
    return reader


def _read(rel: str) -> CodeReading:
    return _reader(rel).read((ROOT / rel).read_text(encoding="utf-8"), {})


def _inline(text: str, name: str = "sample.ts") -> CodeReading:
    return _reader(name).read(text, {})


def _edited(rel: str, old: str, new: str) -> str:
    text = (ROOT / rel).read_text(encoding="utf-8")
    assert text.count(old) == 1, f"{rel} holds {old!r} {text.count(old)} times, not once"
    return text.replace(old, new)


def _shape(reading: CodeReading) -> list[tuple[str, str, int, int, int, bool]]:
    return [(d.symbol, d.kind, d.first, d.line, d.end, d.reachable) for d in reading.definitions()]


def _named(reading: CodeReading, symbol: str) -> Definition:
    return next(d for d in reading.definitions() if d.symbol == symbol)


def _posix(paths: list[Path]) -> list[str]:
    return [path.relative_to(ROOT).as_posix() for path in paths]


def test_fees_lists_each_definition_with_its_lines_and_reach() -> None:
    assert _shape(_read("src/ledger/fees.ts")) == [
        ("GRACE_DAYS", "variable", 3, 3, 3, True),
        ("MAX_FEE", "variable", 5, 5, 5, True),
        ("waived", "function", 7, 7, 7, True),
        ("lateFee", "function", 9, 9, 16, True),
        ("lateDays", "function", 18, 20, 22, True),
    ]


def test_an_exported_definition_starts_at_its_export_keyword() -> None:
    lines = (ROOT / "src/ledger/fees.ts").read_text(encoding="utf-8").splitlines()

    first_lines = {d.symbol: lines[d.first - 1] for d in _read("src/ledger/fees.ts").definitions()}

    assert first_lines == {
        "GRACE_DAYS": "export const GRACE_DAYS = 2;",
        "MAX_FEE": "const MAX_FEE = 500;",
        "waived": "const waived = (days: number): boolean => days <= GRACE_DAYS;",
        "lateFee": "export function lateFee(days: number): number {",
        "lateDays": "export function lateDays(input: string): number;",
    }


def test_a_class_holds_its_fields_and_methods_by_their_kinds() -> None:
    members = [
        (d.symbol, d.kind)
        for d in _read("src/ledger/ledger.ts").definitions()
        if d.scope == ("Ledger",)
    ]

    assert members == [
        ("Ledger.limit", "variable"),
        ("Ledger.ownerName", "variable"),
        ("Ledger.format", "function"),
        ("Ledger.owner", "function"),
        ("Ledger.owner", "function"),
        ("Ledger.remove", "function"),
    ]


def test_a_decorated_method_starts_at_its_first_decorator() -> None:
    remove = _named(_read("src/ledger/ledger.ts"), "Ledger.remove")

    assert (remove.first, remove.line, remove.end) == (19, 22, 24)


def test_a_decorated_class_starts_at_its_decorator() -> None:
    ledger = _named(_read("src/ledger/ledger.ts"), "Ledger")

    assert (ledger.first, ledger.line, ledger.end) == (5, 6, 25)


def test_a_getter_and_a_setter_of_one_name_are_two_definitions_of_that_symbol() -> None:
    owners = [d for d in _read("src/ledger/ledger.ts").definitions() if d.symbol == "Ledger.owner"]

    assert [(d.kind, d.first, d.line, d.end) for d in owners] == [
        ("function", 11, 11, 13),
        ("function", 15, 15, 17),
    ]


def test_an_overload_and_its_implementation_are_one_definition_from_the_first_signature() -> None:
    overloads = [d for d in _read("src/ledger/fees.ts").definitions() if d.symbol == "lateDays"]

    assert [(d.kind, d.first, d.line, d.end) for d in overloads] == [("function", 18, 20, 22)]


def test_the_members_of_an_interface_an_enum_and_an_alias_are_under_their_type() -> None:
    types = {"Loan", "Membership", "Charge"}

    assert [
        (d.symbol, d.kind)
        for d in _read("src/ledger/ledger.ts").definitions()
        if d.symbol.split(".")[0] in types
    ] == [
        ("Loan", "type"),
        ("Loan.title", "variable"),
        ("Loan.daysOut", "function"),
        ("Membership", "type"),
        ("Membership.Basic", "variable"),
        ("Membership.Plus", "variable"),
        ("Charge", "type"),
        ("Charge.cents", "variable"),
    ]


REACHABILITY = """\
const prices = {
  rate(days: number): number {
    return days * 25;
  },
};

export function outer(days: number): number {
  function inner(): number {
    return days;
  }
  if (days > 0) {
    function guarded(): number {
      return 1;
    }
    const block = 2;
  }
  return inner();
}
"""


def test_a_function_no_dotted_path_reaches_is_listed_unreachable_with_no_holder() -> None:
    reading = _inline(REACHABILITY)

    assert [
        (d.symbol, d.reachable, d.holder) for d in reading.definitions() if not d.reachable
    ] == [
        ("rate", False, None),
        ("outer.inner", False, None),
        ("outer.guarded", False, None),
    ]


def test_a_variable_inside_a_block_is_not_listed() -> None:
    assert [d.symbol for d in _inline(REACHABILITY).definitions()] == [
        "prices",
        "rate",
        "outer",
        "outer.inner",
        "outer.guarded",
    ]


def test_a_commonjs_module_method_is_unreachable_and_its_function_is_listed() -> None:
    assert _shape(_read("src/ledger/legacy.js")) == [
        ("plainFee", "function", 3, 3, 5, True),
        ("handler", "function", 8, 8, 10, False),
    ]


def test_the_imports_of_fees_legacy_and_index_name_what_they_bind() -> None:
    def shape(rel: str) -> list[tuple[int, str, list[tuple[str, str | None, str, str | None]]]]:
        return [
            (i.line, i.source, [(n.local, n.name, n.reached_as, n.source) for n in i.names])
            for i in _read(rel).imports()
        ]

    assert shape("src/ledger/fees.ts") == [(1, "./rates", [("rates", "rates", "rates", None)])]
    assert shape("src/ledger/legacy.js") == [
        (1, "./fees", [("lateFee", "lateFee", "lateFee", None)])
    ]
    assert shape("src/ledger/index.ts") == [(1, "./fees", []), (2, "./rates", [])]


IMPORT_FORMS = """\
import loans from "./loans";
import * as desk from "./desk";
import { fee as lateCharge } from "./fees";
import type { Loan } from "./loan";
import legacy = require("./legacy");
import "./polyfill";

export async function load(): Promise<void> {
  await import("./api");
}
"""


def test_each_import_form_names_its_bindings_and_scope() -> None:
    seen = [
        (i.line, i.source, [(n.local, n.name, n.reached_as, n.source) for n in i.names], i.scope)
        for i in _inline(IMPORT_FORMS).imports()
    ]

    assert seen == [
        (1, "./loans", [("loans", "default", "loans", None)], ()),
        (2, "./desk", [("desk", None, "desk", None)], ()),
        (3, "./fees", [("lateCharge", "fee", "lateCharge", None)], ()),
        (4, "./loan", [("Loan", "Loan", "Loan", None)], ()),
        (5, "./legacy", [("legacy", None, "legacy", None)], ()),
        (6, "./polyfill", [], ()),
        (9, "./api", [], ("load",)),
    ]


VITEST_MOCK = """\
import { lateFee } from "./fees";

vi.mock("./fees", async () => {
  const actual = await importOriginal<typeof import("./api")>();
  return actual;
});

export function later(): number {
  return lateFee(1);
}
"""


def test_a_file_with_a_syntax_error_still_answers_its_imports_and_its_function() -> None:
    reading = _inline(VITEST_MOCK)

    assert reading.parsed is False
    assert [(i.line, i.source) for i in reading.imports()] == [(1, "./fees"), (4, "./api")]
    assert _shape(reading) == [("later", "function", 8, 8, 10, True)]


def test_an_absent_name_is_unreadable_in_a_file_that_did_not_parse(tmp_path: Path) -> None:
    write(tmp_path, "src/mock.ts", VITEST_MOCK)
    write(tmp_path, "src/clean.ts", VITEST_MOCK.replace('<typeof import("./api")>', ""))

    assert resolve(tmp_path, Anchor(1, "", "src/mock.ts", "absent", None)).status == "unreadable"
    assert (
        resolve(tmp_path, Anchor(1, "", "src/clean.ts", "absent", None)).status == "missing_symbol"
    )


def test_a_relative_specifier_names_the_file_beside_its_importer() -> None:
    found = _read("src/ledger/fees.ts").files(
        "./rates", ROOT / "src/ledger/fees.ts", [ROOT / "src"]
    )

    assert _posix(found) == ["src/ledger/rates.ts"]


def test_a_relative_specifier_from_a_test_names_the_source_file() -> None:
    found = _read("tests/fees.test.ts").files(
        "../src/ledger/fees", ROOT / "tests/fees.test.ts", [ROOT / "src"]
    )

    assert _posix(found) == ["src/ledger/fees.ts"]


def test_a_specifier_written_with_js_names_the_typescript_file() -> None:
    found = _read("src/ledger/view.tsx").files(
        "./fees.js", ROOT / "src/ledger/view.tsx", [ROOT / "src"]
    )

    assert _posix(found) == ["src/ledger/fees.ts"]


def test_a_directory_specifier_names_its_index_file() -> None:
    found = _read("tests/fees.test.ts").files(
        "../src/ledger", ROOT / "tests/fees.test.ts", [ROOT / "src"]
    )

    assert _posix(found) == ["src/ledger/index.ts"]


def test_a_bare_specifier_names_no_file_even_when_a_sibling_has_its_name() -> None:
    reading = _read("src/ledger/fees.ts")
    importer = ROOT / "src/ledger/fees.ts"

    assert {
        spec: _posix(reading.files(spec, importer, [ROOT / "src"]))
        for spec in ("react", "@/ledger/fees", "rates")
    } == {"react": [], "@/ledger/fees": [], "rates": []}


def test_the_references_of_late_fee_are_its_reads_bindings_and_attributes() -> None:
    reading = _read("src/ledger/fees.ts")

    refs = reading.references(_named(reading, "lateFee"))

    assert refs.names == frozenset({"waived", "days", "rates", "charged", "Math", "MAX_FEE"})
    assert refs.attributes == frozenset({("rates", "daily"), ("Math", "min")})
    assert refs.bound == frozenset({"days", "charged"})


REFORMATS = [
    pytest.param(
        "const fee = lateFee(\n  days,\n  rate,\n);\n",
        "const fee = lateFee(days, rate);\n",
        "sample.ts",
        id="a-trailing-comma-from-rewrapping-a-call",
    ),
    pytest.param(
        "const fee = lateFee(days);\n",
        "const fee = lateFee(days)\n",
        "sample.ts",
        id="a-semicolon",
    ),
    pytest.param(
        'const label = "late fee";\n',
        "const label = 'late fee';\n",
        "sample.ts",
        id="a-string-in-single-or-double-quotes",
    ),
    pytest.param(
        "const fee = (days * 25);\n",
        "const fee = days * 25;\n",
        "sample.ts",
        id="parentheses-a-formatter-adds",
    ),
    pytest.param(
        "// the fee\nconst fee = lateFee(days);\n",
        "const fee = lateFee(days);\n",
        "sample.ts",
        id="a-comment-added",
    ),
    pytest.param(
        "<p>\n    Due in {days} days\n  </p>\n",
        "<p>Due in {days} days</p>\n",
        "view.tsx",
        id="jsx-text-rewrapped-over-lines",
    ),
]


@pytest.mark.parametrize(("before", "after", "name"), REFORMATS)
def test_a_reformat_or_a_comment_leaves_the_canonical_text_alone(
    before: str, after: str, name: str
) -> None:
    assert _inline(before, name).canonical() == _inline(after, name).canonical()


CHANGES = [
    pytest.param("const fee = days + 1;\n", "const fee = days - 1;\n", id="plus-and-minus"),
    pytest.param(
        "const fee = (days + 1) * 2;\n",
        "const fee = days + 1 * 2;\n",
        id="parentheses-that-change-precedence",
    ),
    pytest.param('const label = "a fee";\n', 'const label = "a  fee";\n', id="string-spacing"),
    pytest.param("const holes = [1,,2];\n", "const holes = [1, 2];\n", id="an-array-hole"),
    pytest.param("const fee = 1;\n", "let fee = 1;\n", id="const-and-let"),
]


@pytest.mark.parametrize(("before", "after"), CHANGES)
def test_a_changed_token_changes_the_canonical_text(before: str, after: str) -> None:
    assert _inline(before).canonical() != _inline(after).canonical()


def test_a_changed_decorator_changes_the_canonical_text_of_its_method() -> None:
    before = _read("src/ledger/ledger.ts").canonical("Ledger.remove")
    after = _inline(
        _edited("src/ledger/ledger.ts", '@audit("remove")', '@audit("delete")')
    ).canonical("Ledger.remove")

    assert before is not None
    assert before != after


def test_a_changed_overload_signature_changes_the_canonical_text_of_its_function() -> None:
    before = _read("src/ledger/fees.ts").canonical("lateDays")
    after = _inline(
        _edited(
            "src/ledger/fees.ts",
            "export function lateDays(input: string): number;",
            "export function lateDays(input: boolean): number;",
        )
    ).canonical("lateDays")

    assert before is not None
    assert before != after


def test_a_changed_setter_body_changes_the_canonical_text_of_the_getter_and_setter() -> None:
    before = _read("src/ledger/ledger.ts").canonical("Ledger.owner")
    after = _inline(
        _edited("src/ledger/ledger.ts", "this.ownerName = name;", "this.ownerName = name.trim();")
    ).canonical("Ledger.owner")

    assert before is not None
    assert before != after


def test_the_test_file_offers_its_named_function_as_a_test() -> None:
    assert [d.symbol for d in _read("tests/fees.test.ts").tests()] == ["chargeFor"]


def test_a_function_is_no_test_in_a_file_that_holds_no_test_call() -> None:
    """A test is a call, so a file with none has no test, whatever functions it defines. A
    regular expression's `test` and a route's handler are not test calls."""
    assert _read("src/ledger/fees.ts").tests() == ()
    source = (
        "export function lateFee(days: number) {\n  return days;\n}\n"
        'const late = /late/.test("late");\n'
        'app.get("/fees", () => lateFee(1));\n'
    )

    assert _inline(source).tests() == ()


@pytest.mark.parametrize(
    "call",
    [
        'test("caps the fee", () => {});',
        'it("caps the fee", async () => {});',
        'describe("fees", function () {});',
        "test.only(`caps the fee`, () => {});",
        'Deno.test("caps the fee", { permissions: {} }, () => {});',
    ],
)
def test_a_file_that_holds_a_test_call_offers_the_functions_it_defines(call: str) -> None:
    text = f"function chargeFor() {{\n  return 1;\n}}\n\n{call}\n"

    assert [d.symbol for d in _inline(text, "fees.test.ts").tests()] == ["chargeFor"]


def test_a_source_function_does_not_give_its_name_up_to_a_second_definition(
    fixture_repo: Callable[[str], Path],
) -> None:
    """Two definitions share `waived`, so a bare span names neither. Only a test leaves a
    shared name to the other definition, and a function in a source file is no test."""
    root = fixture_repo("typescript-ledger")
    write(root, "src/ledger/fees.py", "def waived(days):\n    return days < 3\n")
    resolver = CodeResolver(SourceTree(root, load(root / "irminsul.toml")))

    assert resolver.resolve("waived()") == []


def test_a_file_is_mentioned_by_its_stem_and_an_index_file_by_its_directory() -> None:
    reader = _reader("src/ledger/fees.ts")

    assert reader.mentioned_as(Path("src/ledger/fees.ts")) == frozenset({"fees"})
    assert reader.mentioned_as(Path("src/ledger/index.ts")) == frozenset({"ledger"})


def test_a_call_span_naming_a_function_resolves_to_its_definition_and_last_line(
    fixture_repo: Callable[[str], Path],
) -> None:
    root = fixture_repo("typescript-ledger")
    resolver = CodeResolver(SourceTree(root, load(root / "irminsul.toml")))

    assert resolver.resolve("lateFee()") == [
        Reference("lateFee()", "symbol", "lateFee", "src/ledger/fees.ts", 9, 16)
    ]


def test_an_edit_to_a_function_queues_the_guide_that_names_it(
    fixture_repo: Callable[[str], Path],
) -> None:
    root = fixture_repo("typescript-ledger")
    seed_repo(root, when=SEEDED)
    replace_text(
        root,
        "src/ledger/fees.ts",
        "const charged = days * rates.daily;",
        "const charged = days * rates.daily * 2;",
    )

    items = invoke_json(root, "list", "review", "--changed")["items"]

    [item] = [item for item in items if "names-changed-code" in item["markers"]]
    assert item["path"] == "docs/guides/usage.md"
    assert item["changed_code"] == [
        {
            "span": "lateFee()",
            "identity": "lateFee",
            "path": "src/ledger/fees.ts",
            "line": 14,
            "removed": False,
        }
    ]


def test_context_lists_the_test_that_imports_a_file_with_that_reason(
    fixture_repo: Callable[[str], Path],
) -> None:
    root = fixture_repo("typescript-ledger")
    git_init(root)
    commit_all(root, "source", when=SEEDED, paths=["src", "docs", "irminsul.toml"])
    commit_all(root, "tests", when=SEEDED, paths=["tests"])

    [result] = invoke_json(root, "context", "src/ledger/fees.ts")["results"]

    assert result["tests"] == ["tests/fees.test.ts"]
    assert result["test_reasons"]["tests/fees.test.ts"] == ["imports src/ledger/fees.ts"]


def test_suggest_offers_the_test_function_that_calls_late_fee(
    fixture_repo: Callable[[str], Path],
) -> None:
    root = fixture_repo("typescript-ledger")

    report = invoke_json(root, "anchors", "--suggest", "--doc", "docs/guides/usage.md")

    [row] = [row for row in report["resolved"] if row["name"] == "lateFee"]
    assert [(t["path"], t["symbol"], t["marker"]) for t in row["tests"]] == [
        (
            "tests/fees.test.ts",
            "chargeFor",
            "<!-- anchor: tests/fees.test.ts#chargeFor -->",
        )
    ]


def _anchored_copy(fixture_repo: Callable[[str], Path], anchor: str) -> Path:
    root = fixture_repo("typescript-ledger")
    write_doc(
        root,
        PINS,
        doc_id="pins",
        body=f"Late fees grow by the day. <!-- anchor: {anchor} -->",
    )
    return root


def test_a_pinned_function_is_clean_after_an_edit_to_its_comment(
    fixture_repo: Callable[[str], Path],
) -> None:
    root = _anchored_copy(fixture_repo, "src/ledger/fees.ts#lateFee")
    code, output = invoke(root, "anchors", "--re-pin", "--doc", PINS)
    assert code == 0, output

    replace_text(
        root,
        "src/ledger/fees.ts",
        "// The fee grows by the daily rate and stops at the cap.",
        "// Grows by the daily rate, up to the cap.",
    )

    assert run_check(ClaimAnchorCheck, root) == []


def test_a_pinned_function_drifts_after_an_edit_to_its_body(
    fixture_repo: Callable[[str], Path],
) -> None:
    root = _anchored_copy(fixture_repo, "src/ledger/fees.ts#lateFee")
    code, output = invoke(root, "anchors", "--re-pin", "--doc", PINS)
    assert code == 0, output

    replace_text(
        root,
        "src/ledger/fees.ts",
        "return Math.min(charged, MAX_FEE);",
        "return Math.min(charged + 1, MAX_FEE);",
    )

    assert [f.code for f in run_check(ClaimAnchorCheck, root)] == ["claim-anchor/pinned-drift"]


def test_an_anchor_to_a_local_variable_is_a_missing_symbol(
    fixture_repo: Callable[[str], Path],
) -> None:
    root = _anchored_copy(fixture_repo, "src/ledger/fees.ts#charged")

    assert [f.code for f in run_check(ClaimAnchorCheck, root)] == ["claim-anchor/missing-symbol"]
