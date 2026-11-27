"""Rust's reader answers the language interface through tree-sitter, and reads the `use` trees and
the crate paths that its query file cannot say. The fixture `rust-loans` is the Rust code under
test; a few cases that do not belong in a codebase are short inline samples."""

from __future__ import annotations

import datetime as _dt
from collections.abc import Callable
from pathlib import Path

from irminsul.checks.claim_anchor import ClaimAnchorCheck
from irminsul.checks.dependency_check import DependencyCheck
from irminsul.code_references import CodeResolver
from irminsul.config import load
from irminsul.languages import reader_for
from irminsul.languages.reader import CodeReading, Definition
from irminsul.languages.rust_reader import RUST_READER
from irminsul.source_tree import SourceTree

from .conftest import (
    FIXTURE_REPOS_DIR,
    invoke,
    invoke_json,
    replace_text,
    run_check,
    seed_repo,
    write,
    write_doc,
)

LOANS = FIXTURE_REPOS_DIR / "rust-loans"
FEES = "src/loans/fees.rs"
SEEDED = _dt.datetime(2024, 1, 1, 12, tzinfo=_dt.UTC)

DESK_IMPLS = """\
pub struct Desk;

impl Desk {
    pub fn open(&self) -> bool {
        true
    }
}

pub trait Opener {
    fn open(&self) -> bool;
}

impl Opener for Desk {
    fn open(&self) -> bool {
        false
    }
}
"""

DESK_DOC = "docs/components/desk.md"


def _text(rel: str) -> str:
    return (LOANS / rel).read_text(encoding="utf-8")


def _fixture(rel: str) -> CodeReading:
    """The fixture's file `rel`, read by the reader its suffix names."""
    reader = reader_for(rel)
    assert reader is not None
    return reader.read(_text(rel))


def _named(reading: CodeReading, symbol: str) -> Definition:
    found = [d for d in reading.definitions() if d.symbol == symbol]
    assert len(found) == 1, f"{symbol} is defined {len(found)} times, not once"
    return found[0]


def _edited(text: str, old: str, new: str) -> str:
    """`text` with its one occurrence of `old` replaced by `new`, so a variant always differs
    from the fixture in exactly the place the test names."""
    assert text.count(old) == 1, old
    return text.replace(old, new)


def _imports(reading: CodeReading) -> list[tuple[object, ...]]:
    return [
        (i.line, i.source, i.scope, [(n.local, n.name, n.reached_as, n.source) for n in i.names])
        for i in reading.imports()
    ]


def _files(source: str, importer: str, root: Path = LOANS) -> list[str]:
    """The files the path `source` may be, from `importer` under `root`, as repository paths."""
    found = RUST_READER.read("").files(source, root / importer, [root / "src"])
    return [path.relative_to(root).as_posix() for path in found]


def _resolver(root: Path) -> CodeResolver:
    return CodeResolver(SourceTree(root, load(root / "irminsul.toml")))


def _pin_desk(root: Path) -> None:
    """A doc whose one paragraph anchors `Desk::new`, pinned at the fixture's current code."""
    write_doc(
        root,
        DESK_DOC,
        doc_id="desk",
        body="A desk opens with `Desk::new()`.\n<!-- anchor: src/loans/fees.rs#Desk::new -->",
    )
    code, output = invoke(root, "anchors", "--re-pin", "--doc", DESK_DOC)
    assert code == 0, output


def test_the_definitions_of_fees_are_listed_in_file_order_with_their_lines_and_reach() -> None:
    fees = _fixture(FEES)

    assert [
        (d.symbol, d.kind, d.first, d.line, d.end, d.reachable) for d in fees.definitions()
    ] == [
        ("RATE", "variable", 5, 5, 5, True),
        ("GRACE", "variable", 6, 6, 6, True),
        ("weeks", "function", 8, 8, 12, True),
        ("late_fee", "function", 15, 15, 18, True),
        ("grace_day", "function", 21, 21, 27, True),
        ("grace_day.round_up", "function", 22, 22, 24, False),
        ("Desk", "type", 30, 33, 36, True),
        ("Desk.name", "variable", 34, 34, 34, True),
        ("Desk.day", "variable", 35, 35, 35, True),
        ("Fee", "type", 38, 38, 41, True),
        ("Fee.Waived", "variable", 39, 39, 39, True),
        ("Fee.Charged", "variable", 40, 40, 40, True),
        ("Opener", "type", 43, 43, 49, True),
        ("Opener.open", "function", 44, 44, 44, True),
        ("Opener.is_open", "function", 46, 46, 48, True),
        ("Desk.new", "function", 52, 52, 57, True),
        ("Desk.open_days", "function", 59, 60, 62, True),
        ("Desk.open", "function", 66, 66, 68, True),
        ("Stack", "type", 71, 71, 71, True),
        ("Stack.open", "function", 74, 74, 76, True),
        ("open", "function", 80, 80, 82, False),
        ("tests.late_fee", "function", 89, 90, 93, True),
        ("tests.fee_is_waived_on_time", "function", 95, 96, 98, True),
        ("tests.charged", "function", 100, 100, 102, True),
    ]


def test_the_attributes_above_a_struct_join_its_first_line_past_the_comments_between() -> None:
    desk = _named(_fixture(FEES), "Desk")

    assert (desk.first, desk.line) == (30, 33)


def test_a_function_in_an_impl_block_is_held_by_the_type_the_block_is_for() -> None:
    fees = _fixture(FEES)

    assert [
        _named(fees, symbol).holder for symbol in ("Desk.new", "Desk.open_days", "Stack.open")
    ] == [
        "Desk",
        "Desk",
        "Stack",
    ]


def test_a_function_in_an_impl_for_a_reference_type_is_not_reachable() -> None:
    blanket = _named(_fixture(FEES), "open")

    assert (blanket.line, blanket.reachable, blanket.holder, blanket.scope) == (80, False, None, ())


def test_a_function_in_mod_tests_is_held_by_tests() -> None:
    fees = _fixture(FEES)

    assert [
        (d.symbol, d.holder, d.reachable) for d in fees.definitions() if d.scope == ("tests",)
    ] == [
        ("tests.late_fee", "tests", True),
        ("tests.fee_is_waived_on_time", "tests", True),
        ("tests.charged", "tests", True),
    ]


def test_a_trait_method_signature_and_a_method_with_a_body_are_both_under_the_trait() -> None:
    fees = _fixture(FEES)

    assert [
        (d.symbol, d.kind, d.holder, d.line) for d in fees.definitions() if d.scope == ("Opener",)
    ] == [
        ("Opener.open", "function", "Opener", 44),
        ("Opener.is_open", "function", "Opener", 46),
    ]


def test_struct_fields_and_enum_variants_are_variables_under_their_type() -> None:
    fees = _fixture(FEES)

    assert [
        (d.symbol, d.kind, d.holder)
        for d in fees.definitions()
        if d.kind == "variable" and d.holder is not None
    ] == [
        ("Desk.name", "variable", "Desk"),
        ("Desk.day", "variable", "Desk"),
        ("Fee.Waived", "variable", "Fee"),
        ("Fee.Charged", "variable", "Fee"),
    ]


def test_a_macro_rules_definition_is_a_function() -> None:
    weeks = _named(_fixture(FEES), "weeks")

    assert (weeks.kind, weeks.line, weeks.end, weeks.reachable) == ("function", 8, 12, True)


def test_an_extern_blocks_items_are_reached_from_the_module_the_block_is_in() -> None:
    reader = reader_for("src/ffi.rs")
    assert reader is not None
    reading = reader.read(
        'extern "C" {\n    fn puts(s: *const u8) -> i32;\n    static ERRNO: i32;\n}\n'
    )

    assert [(d.symbol, d.kind, d.line, d.reachable) for d in reading.definitions()] == [
        ("puts", "function", 2, True),
        ("ERRNO", "variable", 3, True),
    ]


def test_a_traits_associated_type_is_a_type_under_the_trait() -> None:
    reader = reader_for("src/shelf.rs")
    assert reader is not None
    reading = reader.read(
        "pub trait Shelf {\n    type Item;\n    fn first(&self) -> Self::Item;\n}\n"
    )

    assert [(d.symbol, d.kind, d.line, d.reachable) for d in reading.definitions()] == [
        ("Shelf", "type", 1, True),
        ("Shelf.Item", "type", 2, True),
        ("Shelf.first", "function", 3, True),
    ]


def test_a_function_declared_in_a_function_body_is_not_reachable() -> None:
    round_up = _named(_fixture(FEES), "grace_day.round_up")

    assert (round_up.line, round_up.reachable, round_up.holder) == (22, False, None)


def test_the_imports_of_fees_bind_each_name_under_its_alias_or_its_module() -> None:
    assert _imports(_fixture(FEES)) == [
        (1, "super", (), [("policy", "policy", "policy", "super::policy")]),
        (
            2,
            "crate::loans::policy",
            (),
            [
                ("due_day", "due_day", "due_day", "crate::loans::policy::due_day"),
                ("CAP", "LIMIT", "CAP", "crate::loans::policy::LIMIT"),
            ],
        ),
        (
            3,
            "crate::util",
            (),
            [("util", None, "util", None), ("clamp", "clamp", "clamp", "crate::util::clamp")],
        ),
        (87, "self", ("tests",), [("*", "*", "*", None)]),
    ]


def test_a_use_tree_binds_each_leaf_under_the_module_path_before_it() -> None:
    assert _imports(RUST_READER.read("use a::{b::{c, d}, e};\nuse f::*;\n")) == [
        (1, "a::b", (), [("c", "c", "c", "a::b::c"), ("d", "d", "d", "a::b::d")]),
        (1, "a", (), [("e", "e", "e", "a::e")]),
        (2, "f", (), [("*", "*", "*", None)]),
    ]


def test_a_crate_or_super_path_in_fees_is_the_module_file_or_its_mod_rs() -> None:
    assert _files("crate::loans::policy", FEES) == [
        "src/loans/policy.rs",
        "src/loans/policy/mod.rs",
    ]
    assert _files("super::policy", FEES) == ["src/loans/policy.rs", "src/loans/policy/mod.rs"]


def test_self_in_fees_is_the_files_own_module() -> None:
    assert _files("self", FEES) == ["src/loans/fees.rs", "src/loans/fees/mod.rs"]


def test_a_path_from_an_integration_test_starts_at_the_package_name_with_underscores() -> None:
    assert _files("rust_loans::loans::fees", "tests/fees.rs") == [
        "src/loans/fees.rs",
        "src/loans/fees/mod.rs",
    ]


def test_a_path_into_no_package_of_the_repository_is_no_file() -> None:
    assert _files("std::collections", FEES) == []
    assert _files("serde::Serialize", FEES) == []


def test_a_lib_table_name_lets_the_crate_be_imported_under_it(tmp_path: Path) -> None:
    _crate(tmp_path)

    assert _files("lending::util", "src/lib.rs", tmp_path) == ["src/util.rs", "src/util/mod.rs"]


def test_a_crate_path_in_a_bin_file_resolves_inside_src_bin(tmp_path: Path) -> None:
    _crate(tmp_path)

    assert _files("crate::helper", "src/bin/report.rs", tmp_path) == [
        "src/bin/helper.rs",
        "src/bin/helper/mod.rs",
    ]


def test_a_crate_path_in_an_integration_test_resolves_inside_tests(tmp_path: Path) -> None:
    _crate(tmp_path)

    assert _files("crate::common", "tests/it.rs", tmp_path) == [
        "tests/common.rs",
        "tests/common/mod.rs",
    ]


def test_a_file_with_no_cargo_toml_above_it_places_nothing(tmp_path: Path) -> None:
    write(tmp_path, "loose/fees.rs", "")

    assert _files("crate::util", "loose/fees.rs", tmp_path) == []


def _crate(root: Path) -> None:
    """A package named `loans-app` whose library is named `lending`, with the files the path
    tests name, empty, since the placement reads only where they are."""
    write(
        root,
        "Cargo.toml",
        '[package]\nname = "loans-app"\nversion = "0.1.0"\nedition = "2021"\n\n'
        '[lib]\nname = "lending"\n',
    )
    for rel in (
        "src/lib.rs",
        "src/util.rs",
        "src/bin/report.rs",
        "src/bin/helper.rs",
        "tests/it.rs",
        "tests/common.rs",
        "tests/common/mod.rs",
    ):
        write(root, rel, "")


def test_a_body_refers_to_the_names_it_reads_and_binds_its_own() -> None:
    fees = _fixture(FEES)

    refs = fees.references(_named(fees, "late_fee"))

    assert refs.names == frozenset({"CAP", "RATE", "due_day", "entered", "late", "paid", "util"})
    assert refs.attributes == frozenset({("paid", "saturating_sub"), ("util", "clamp")})
    assert refs.bound == frozenset({"entered", "late", "paid"})
    assert refs.imports == ()


def test_the_name_read_at_the_end_of_a_path_is_an_attribute_of_its_head() -> None:
    fees = _fixture(FEES)

    refs = fees.references(_named(fees, "late_fee"))

    assert ("util", "clamp") in refs.attributes
    assert "clamp" not in refs.names


def test_canonical_text_ignores_a_structs_line_breaks_trailing_comma_and_doc_comments() -> None:
    text = _text(FEES)
    one_line = _edited(
        text,
        "pub struct Desk {\n    pub name: String,\n    pub day: u32,\n}\n",
        "pub struct Desk { pub name: String, pub day: u32 }\n",
    )
    documented = _edited(
        text, "#[derive(Debug, Clone)]\n", "/// Shown in the shop.\n#[derive(Debug, Clone)]\n"
    )

    base = RUST_READER.read(text).canonical("Desk")

    assert base is not None
    assert RUST_READER.read(one_line).canonical("Desk") == base
    assert RUST_READER.read(documented).canonical("Desk") == base


def test_canonical_text_tells_a_raw_string_from_a_raw_byte_string() -> None:
    raw = RUST_READER.read('pub const TAG: &[u8] = r"a";\n').canonical("TAG")
    byte = RUST_READER.read('pub const TAG: &[u8] = br"a";\n').canonical("TAG")

    assert raw is not None and byte is not None
    assert raw != byte


def test_canonical_text_keeps_a_derive_above_a_struct_with_a_comment_between() -> None:
    text = _text(FEES)
    derived = _edited(text, "#[derive(Debug, Clone)]\n", "#[derive(Debug, Clone, PartialEq)]\n")

    base = RUST_READER.read(text).canonical("Desk")

    assert base is not None
    assert RUST_READER.read(derived).canonical("Desk") != base


def test_canonical_text_of_a_symbol_changes_when_only_its_second_impl_block_does() -> None:
    base = RUST_READER.read(DESK_IMPLS).canonical("Desk.open")
    second_changed = _edited(DESK_IMPLS, "        false\n", "        true\n")

    assert base is not None
    assert RUST_READER.read(second_changed).canonical("Desk.open") != base


def test_canonical_text_tells_a_block_value_from_a_statement_before_one() -> None:
    value = RUST_READER.read("fn f() -> i32 { g() }\n").canonical("f")
    statement = RUST_READER.read("fn f() -> i32 { g(); 1 }\n").canonical("f")

    assert value is not None and statement is not None
    assert value != statement


def test_the_tests_of_fees_are_its_test_functions_under_their_module() -> None:
    assert [d.symbol for d in _fixture(FEES).tests()] == [
        "tests.late_fee",
        "tests.fee_is_waived_on_time",
    ]


def test_the_only_test_of_the_integration_test_file_is_fee_is_capped() -> None:
    assert [d.symbol for d in _fixture("tests/fees.rs").tests()] == ["fee_is_capped"]


def test_a_symbol_is_found_by_either_the_double_colon_or_the_dotted_spelling() -> None:
    fees = _fixture(FEES)

    assert fees.canonical("Desk::new") is not None
    assert fees.canonical("Desk::new") == fees.canonical("Desk.new")


def test_mentioned_as_is_a_files_stem_or_its_directory_for_mod_rs() -> None:
    assert RUST_READER.mentioned_as(Path("src/loans/fees.rs")) == frozenset({"fees"})
    assert RUST_READER.mentioned_as(Path("src/loans/mod.rs")) == frozenset({"loans"})


def test_mentioned_as_is_none_for_a_crate_root() -> None:
    assert RUST_READER.mentioned_as(Path("src/lib.rs")) is None


def test_a_bare_name_resolves_to_the_function_not_to_the_test_of_the_same_name(
    fixture_repo: Callable[[str], Path],
) -> None:
    resolver = _resolver(fixture_repo("rust-loans"))

    assert [
        (r.kind, r.identity, r.defined_at, r.line, r.line_end)
        for r in resolver.resolve("late_fee()")
    ] == [("symbol", "late_fee", FEES, 15, 18)]


def test_a_double_colon_path_resolves_to_the_method_it_names(
    fixture_repo: Callable[[str], Path],
) -> None:
    resolver = _resolver(fixture_repo("rust-loans"))

    assert [
        (r.kind, r.identity, r.defined_at, r.line, r.line_end)
        for r in resolver.resolve("Desk::new()")
    ] == [("symbol", "new", FEES, 52, 57)]


def test_an_unbacked_depends_on_is_silent_because_rust_does_not_place_every_import(
    fixture_repo: Callable[[str], Path],
) -> None:
    root = fixture_repo("rust-loans")

    assert run_check(DependencyCheck, root) == []


def test_context_names_the_integration_test_that_imports_the_file(
    fixture_repo: Callable[[str], Path],
) -> None:
    root = fixture_repo("rust-loans")
    seed_repo(root, when=SEEDED)

    [result] = invoke_json(root, "context", FEES)["results"]

    assert result["tests"] == ["tests/fees.rs"]
    assert result["test_reasons"] == {
        "tests/fees.rs": [f"imports {FEES}", "changed with it in 1 commit"]
    }


def test_suggest_offers_the_integration_test_that_calls_the_function_a_guide_names(
    fixture_repo: Callable[[str], Path],
) -> None:
    root = fixture_repo("rust-loans")

    assert invoke_json(root, "anchors", "--suggest", "--doc", "docs/guides/lending.md") == {
        "version": 1,
        "unbound": [],
        "resolved": [
            {
                "path": "docs/guides/lending.md",
                "line": 11,
                "name": "late_fee",
                "definition": {"path": FEES, "line": 15},
                "tests": [
                    {
                        "path": "tests/fees.rs",
                        "line": 4,
                        "symbol": "fee_is_capped",
                        "marker": "<!-- anchor: tests/fees.rs#fee_is_capped -->",
                    }
                ],
            }
        ],
    }


def test_an_edit_to_a_rust_function_queues_the_guide_that_names_it(
    fixture_repo: Callable[[str], Path],
) -> None:
    root = fixture_repo("rust-loans")
    seed_repo(root, when=SEEDED)
    replace_text(
        root, FEES, "util::clamp(late * RATE, 0, CAP)", "util::clamp(late * RATE * 2, 0, CAP)"
    )

    items = invoke_json(root, "list", "review", "--changed")["items"]

    [item] = [item for item in items if "names-changed-code" in item["markers"]]
    assert item["path"] == "docs/guides/lending.md"
    assert item["changed_code"] == [
        {"span": "late_fee()", "identity": "late_fee", "path": FEES, "line": 17, "removed": False}
    ]


def test_a_comment_inside_a_pinned_method_leaves_its_anchor_clean(
    fixture_repo: Callable[[str], Path],
) -> None:
    root = fixture_repo("rust-loans")
    _pin_desk(root)
    replace_text(
        root,
        FEES,
        "    pub fn new() -> Self {\n",
        "    pub fn new() -> Self {\n        // A new desk has no day booked yet.\n",
    )

    assert run_check(ClaimAnchorCheck, root) == []


def test_an_edit_to_a_pinned_methods_body_is_pinned_drift(
    fixture_repo: Callable[[str], Path],
) -> None:
    root = fixture_repo("rust-loans")
    _pin_desk(root)
    replace_text(root, FEES, "            day: 0,\n", "            day: 1,\n")

    assert [finding.code for finding in run_check(ClaimAnchorCheck, root)] == [
        "claim-anchor/pinned-drift"
    ]
