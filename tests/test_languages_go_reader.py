"""Go's reader answers the language interface from the go-library fixture's files: what a
file defines and imports, which package files an import places, what a body refers to, what
text a pin hashes, and which tests a file holds. The commands read it through the docs that
name its code.
"""

from __future__ import annotations

import datetime as _dt
from collections.abc import Callable
from pathlib import Path

from irminsul.checks.claim_anchor import ClaimAnchorCheck
from irminsul.checks.dependency_check import DependencyCheck
from irminsul.languages import READERS, reader_for
from irminsul.languages.go_reader import GO_READER
from irminsul.languages.reader import CodeReading, Definition

from .conftest import (
    FIXTURE_REPOS_DIR,
    invoke,
    invoke_json,
    load_graph,
    replace_text,
    run_check,
    seed_repo,
    write,
    write_config,
)

SEEDED = _dt.datetime(2024, 1, 1, 12, tzinfo=_dt.UTC)

GO_LIBRARY = FIXTURE_REPOS_DIR / "go-library"
DESK = GO_LIBRARY / "internal" / "desk" / "desk.go"
LEDGER = GO_LIBRARY / "internal" / "desk" / "ledger.go"
DESK_TEST = GO_LIBRARY / "internal" / "desk" / "desk_test.go"
POLICY = GO_LIBRARY / "internal" / "policy" / "policy.go"
POLICY_TEST = GO_LIBRARY / "internal" / "policy" / "policy_test.go"
INTERNAL = GO_LIBRARY / "internal"
SAMPLE = Path("sample.go")

RATES_ONE_LINE = 'package p\n\nvar rates = map[string]int{"daily": 25, "weekly": 150}\n'

RATES_WRAPPED = """\
package p

var rates = map[string]int{
	"daily":  25,
	"weekly": 150,
}
"""

RATES_COMMENTED = """\
package p

var rates = map[string]int{
	// the daily and the weekly rate
	"daily":  25,
	"weekly": 150,
}
"""

FOR_INIT_ONLY = "package p\n\nfunc run(x bool) {\n\tfor x; ; {\n\t}\n}\n"
FOR_CONDITION_ONLY = "package p\n\nfunc run(x bool) {\n\tfor ; x; {\n\t}\n}\n"

TWO_INITS = "package p\n\nfunc init() {\n\tsetup(1)\n}\n\nfunc init() {\n\tsetup(2)\n}\n"

ANCHORED_PARAGRAPH = (
    "\nThe loan is posted once the item is out.\n"
    "<!-- anchor: internal/desk/desk.go#Desk.CheckOut -->\n"
)


def _reading(path: Path, text: str | None = None) -> CodeReading:
    reader = reader_for(path)
    assert reader is not None
    return reader.read(path.read_text(encoding="utf-8") if text is None else text, {})


def _named(reading: CodeReading, symbol: str) -> Definition:
    return next(d for d in reading.definitions() if d.symbol == symbol)


def _edited(text: str, old: str, new: str) -> str:
    """`text` with its one occurrence of `old` replaced by `new`."""
    assert text.count(old) == 1, f"{old!r} occurs {text.count(old)} times, not once"
    return text.replace(old, new)


def _relative(paths: list[Path], root: Path) -> list[str]:
    return [path.relative_to(root).as_posix() for path in paths]


def test_the_go_profile_names_its_reader() -> None:
    assert READERS["go"] is GO_READER
    assert reader_for(DESK) is GO_READER


def test_desk_go_lists_each_definition_with_its_lines_and_reachability() -> None:
    """`OnLoan` and `Overdue` have no value of their own: each repeats the expression of
    the constant above it, so what defines one is its whole block, lines 10 to 14."""
    reading = _reading(DESK)

    assert [
        (d.symbol, d.kind, d.first, d.line, d.end, d.reachable) for d in reading.definitions()
    ] == [
        ("Available", "variable", 11, 11, 11, True),
        ("OnLoan", "variable", 10, 12, 14, True),
        ("Overdue", "variable", 10, 13, 14, True),
        ("lateDays", "variable", 16, 16, 16, True),
        ("maxFine", "variable", 16, 16, 16, True),
        ("ledgerSource", "variable", 18, 19, 19, True),
        ("Desk", "type", 22, 22, 25, True),
        ("Desk.loans", "variable", 23, 23, 23, True),
        ("Desk.entries", "variable", 24, 24, 24, True),
        ("Stack", "type", 28, 28, 30, True),
        ("Stack.items", "variable", 29, 29, 29, True),
        ("Stack.Push", "function", 33, 33, 35, True),
        ("Desk.CheckOut", "function", 38, 38, 46, True),
    ]


def test_a_method_is_held_by_its_receivers_type_through_a_pointer_and_a_generic_receiver() -> None:
    reading = _reading(DESK)

    assert (_named(reading, "Desk.CheckOut").holder, _named(reading, "Stack.Push").holder) == (
        "Desk",
        "Stack",
    )


def test_struct_fields_and_an_interface_method_are_definitions_under_their_type() -> None:
    fields = [
        (d.symbol, d.kind, d.holder)
        for d in _reading(DESK).definitions()
        if d.holder == "Desk" and d.kind == "variable"
    ]
    rule = _named(_reading(POLICY), "Rule.Fee")

    assert fields == [("Desk.loans", "variable", "Desk"), ("Desk.entries", "variable", "Desk")]
    assert (rule.kind, rule.holder, rule.line) == ("function", "Rule", 6)


def test_each_name_of_a_var_declaring_two_names_is_a_definition_on_the_same_lines() -> None:
    reading = _reading(DESK)

    assert [
        (d.symbol, d.first, d.line, d.end)
        for d in reading.definitions()
        if d.symbol in ("lateDays", "maxFine")
    ] == [("lateDays", 16, 16, 16), ("maxFine", 16, 16, 16)]


def test_a_constant_with_no_value_changes_when_a_constant_is_inserted_above_it() -> None:
    text = DESK.read_text(encoding="utf-8")
    before = _reading(DESK).canonical("OnLoan")
    after = _reading(DESK, _edited(text, "\tOnLoan\n", "\tReserved\n\tOnLoan\n")).canonical(
        "OnLoan"
    )

    assert before is not None and after is not None
    assert after != before


def test_a_constant_with_a_value_does_not_change_when_a_constant_is_added_below_it() -> None:
    text = DESK.read_text(encoding="utf-8")
    before = _reading(DESK).canonical("Available")
    after = _reading(
        DESK, _edited(text, "\tAvailable = iota\n", "\tAvailable = iota\n\tReserved\n")
    ).canonical("Available")

    assert before is not None and after is not None
    assert after == before


def test_a_go_embed_comment_is_the_first_line_of_the_variable_under_it() -> None:
    ledger_source = _named(_reading(DESK), "ledgerSource")

    assert (ledger_source.first, ledger_source.line) == (18, 19)


def test_a_go_embed_pattern_is_part_of_the_variable_canonical_text() -> None:
    text = DESK.read_text(encoding="utf-8")
    before = _reading(DESK).canonical("ledgerSource")
    after = _reading(DESK, _edited(text, "//go:embed ledger.go", "//go:embed policy.go")).canonical(
        "ledgerSource"
    )

    assert before is not None and after is not None
    assert after != before


def test_an_ordinary_comment_above_a_function_changes_nothing() -> None:
    text = DESK.read_text(encoding="utf-8")
    commented = _edited(text, "// CheckOut lends", "// Lend hands out an item.\n// CheckOut lends")
    before = _reading(DESK).canonical("Desk.CheckOut")
    after = _reading(DESK, commented).canonical("Desk.CheckOut")

    assert before is not None and after is not None
    assert after == before


def test_a_type_declared_inside_a_function_body_is_listed_but_not_reachable() -> None:
    assert [(d.symbol, d.kind, d.reachable) for d in _reading(LEDGER).definitions()] == [
        ("postEntry", "function", True),
        ("postEntry.entry", "type", False),
    ]


def test_desk_go_imports_its_own_package_and_its_two_others_with_lines_and_names() -> None:
    assert [
        (i.line, i.source, [(n.local, n.name, n.reached_as, n.source) for n in i.names], i.scope)
        for i in _reading(DESK).imports()
    ] == [
        (1, ".", [("*", "*", "*", None)], ()),
        (4, "embed", [], ()),
        (5, "fmt", [("fmt", None, "fmt", None)], ()),
        (7, "example.com/library/internal/policy", [("rules", None, "rules", None)], ()),
    ]


def test_a_dot_import_binds_every_name_and_a_blank_import_binds_none() -> None:
    reading = _reading(SAMPLE, 'package p\n\nimport (\n\t. "fmt"\n\t_ "os"\n)\n')

    assert [
        (i.line, i.source, [(n.local, n.name, n.reached_as, n.source) for n in i.names])
        for i in reading.imports()
    ] == [
        (1, ".", [("*", "*", "*", None)]),
        (4, "fmt", [("*", "*", "*", None)]),
        (5, "os", []),
    ]


def test_an_import_binds_its_package_name_without_a_major_version_or_yaml_suffix() -> None:
    reading = _reading(
        SAMPLE, 'package p\n\nimport (\n\t"example.com/lib/v2"\n\t"gopkg.in/yaml.v3"\n)\n'
    )

    assert [
        (i.source, [(n.local, n.name, n.reached_as, n.source) for n in i.names])
        for i in reading.imports()
    ] == [
        (".", [("*", "*", "*", None)]),
        ("example.com/lib/v2", [("lib", None, "lib", None)]),
        ("gopkg.in/yaml.v3", [("yaml", None, "yaml", None)]),
    ]


def test_an_import_of_a_module_package_places_its_files_without_its_tests() -> None:
    files = _reading(DESK).files("example.com/library/internal/policy", DESK, [INTERNAL])

    assert _relative(files, GO_LIBRARY) == ["internal/policy/policy.go"]


def test_a_package_clause_places_the_other_files_of_its_package_but_not_the_file_itself() -> None:
    files = _reading(DESK).files(".", DESK, [INTERNAL])

    assert _relative(files, GO_LIBRARY) == ["internal/desk/ledger.go"]


def test_an_import_of_a_longer_module_name_or_another_module_places_no_file(
    fixture_repo: Callable[[str], Path],
) -> None:
    root = fixture_repo("go-library")
    write(root, "x/internal/policy/leak.go", "package policy\n")
    desk = root / "internal" / "desk" / "desk.go"
    reading = _reading(desk)
    roots = [root / "internal"]

    assert reading.files("fmt", desk, roots) == []
    assert reading.files("github.com/other/thing", desk, roots) == []
    assert reading.files("example.com/libraryx/internal/policy", desk, roots) == []


def test_a_replace_directive_places_the_module_in_its_local_directory(tmp_path: Path) -> None:
    write(
        tmp_path,
        "app/go.mod",
        "module example.com/app\n\ngo 1.22\n\nreplace example.com/shared => ../shared\n",
    )
    write(tmp_path, "app/main.go", "package main\n")
    write(tmp_path, "shared/util/util.go", "package util\n")
    importer = tmp_path / "app" / "main.go"

    files = _reading(importer).files("example.com/shared/util", importer, [tmp_path / "app"])

    assert _relative(files, tmp_path) == ["shared/util/util.go"]


def test_a_go_work_use_block_places_a_module_of_another_directory(tmp_path: Path) -> None:
    write(tmp_path, "go.work", "go 1.22\n\nuse (\n\t./app\n\t./tools\n)\n")
    write(tmp_path, "app/go.mod", "module example.com/app\n\ngo 1.22\n")
    write(tmp_path, "app/main.go", "package main\n")
    write(tmp_path, "tools/go.mod", "module example.com/tools\n\ngo 1.22\n")
    write(tmp_path, "tools/gen/gen.go", "package gen\n")
    importer = tmp_path / "app" / "main.go"

    files = _reading(importer).files("example.com/tools/gen", importer, [tmp_path / "app"])

    assert _relative(files, tmp_path) == ["tools/gen/gen.go"]


def test_an_import_places_no_file_where_no_go_mod_stands_above_the_file(tmp_path: Path) -> None:
    write(tmp_path, "loose/x.go", "package loose\n")
    write(tmp_path, "loose/y.go", "package loose\n")
    importer = tmp_path / "loose" / "x.go"

    files = _reading(importer).files("example.com/library/internal/policy", importer, [tmp_path])

    assert files == []


def test_a_package_clause_places_its_siblings_even_with_no_go_mod(tmp_path: Path) -> None:
    write(tmp_path, "loose/x.go", "package loose\n")
    write(tmp_path, "loose/y.go", "package loose\n")
    importer = tmp_path / "loose" / "x.go"

    files = _reading(importer).files(".", importer, [tmp_path])

    assert _relative(files, tmp_path) == ["loose/y.go"]


def test_a_body_reads_these_bare_names() -> None:
    """`nil` is a literal to the grammar, as `None` is to Python's, and no name a
    definition could answer to."""
    reading = _reading(DESK)

    refs = reading.references(_named(reading, "Desk.CheckOut"))

    assert refs.names == frozenset(
        {
            "Desk",
            "d",
            "error",
            "fine",
            "fmt",
            "item",
            "lateDays",
            "patron",
            "postEntry",
            "rules",
            "string",
        }
    )


def test_a_body_reads_each_attribute_with_the_name_it_is_read_from() -> None:
    reading = _reading(DESK)

    refs = reading.references(_named(reading, "Desk.CheckOut"))

    assert refs.attributes == frozenset(
        {
            ("d", "entries"),
            ("d", "loans"),
            ("fmt", "Errorf"),
            ("fmt", "Sprintf"),
            ("rules", "LateFee"),
        }
    )


def test_a_body_binds_its_receiver_parameters_and_locals() -> None:
    reading = _reading(DESK)

    refs = reading.references(_named(reading, "Desk.CheckOut"))

    assert refs.bound == frozenset({"d", "fine", "item", "patron"})


def test_a_composite_literal_reads_the_same_on_one_line_wrapped_or_commented() -> None:
    one_line = _reading(SAMPLE, RATES_ONE_LINE).canonical("rates")

    assert one_line is not None
    assert _reading(SAMPLE, RATES_WRAPPED).canonical("rates") == one_line
    assert _reading(SAMPLE, RATES_COMMENTED).canonical("rates") == one_line


def test_a_for_loop_with_the_condition_and_the_initializer_swapped_differs() -> None:
    before = _reading(SAMPLE, FOR_INIT_ONLY).canonical("run")
    after = _reading(SAMPLE, FOR_CONDITION_ONLY).canonical("run")

    assert before is not None and after is not None
    assert after != before


def test_the_second_of_two_init_functions_changes_the_canonical_text_of_init() -> None:
    before = _reading(SAMPLE, TWO_INITS).canonical("init")
    after = _reading(SAMPLE, _edited(TWO_INITS, "setup(2)", "setup(3)")).canonical("init")

    assert before is not None and after is not None
    assert after != before


def test_desk_test_go_holds_the_test_and_not_the_helpers() -> None:
    assert [d.symbol for d in _reading(DESK_TEST).tests()] == ["TestCheckOut"]


def test_mentioned_as_holds_the_package_name_of_a_file_in_a_module() -> None:
    assert GO_READER.mentioned_as(POLICY) == frozenset({"policy"})


def test_mentioned_as_holds_both_names_when_the_package_clause_names_another_package() -> None:
    assert GO_READER.mentioned_as(POLICY_TEST) == frozenset({"policy", "policy_test"})


def test_mentioned_as_is_none_outside_any_module(tmp_path: Path) -> None:
    write(tmp_path, "loose/x.go", "package loose\n")

    assert GO_READER.mentioned_as(tmp_path / "loose" / "x.go") is None


def test_a_depends_on_no_import_backs_is_reported_once_and_one_backed_is_not(
    fixture_repo: Callable[[str], Path],
) -> None:
    root = fixture_repo("go-library")

    [finding] = run_check(DependencyCheck, root)

    assert finding.path is not None
    assert (finding.code, finding.path.as_posix(), finding.doc_id) == (
        "import-deps/hallucinated-dependency",
        "docs/components/policy.md",
        "policy",
    )
    assert finding.message == "depends_on 'desk' declared but no import relationship found"


def test_a_package_clause_on_the_first_line_of_a_file_with_a_byte_order_mark_is_read(
    tmp_path: Path,
) -> None:
    """The file's own package name is one of the names a file of the same package spells,
    and the mark an editor saved before `package` does not hide it."""
    write(tmp_path, "go.mod", "module example.com/shop\n")
    plain = write(tmp_path, "cmd/tool/main.go", "package main\n")
    marked = write(tmp_path, "cmd/other/main.go", "\ufeffpackage main\n")

    assert GO_READER.mentioned_as(plain) == frozenset({"tool", "main"})
    assert GO_READER.mentioned_as(marked) == frozenset({"other", "main"})


def test_a_go_file_that_is_not_utf8_denies_no_dependency(tmp_path: Path) -> None:
    """The cart imports nothing, so its doc's `depends_on` is reported. Saved as Latin-1 its
    text is not read, no import of it is known, and the report goes."""
    write(tmp_path, "go.mod", "module example.com/shop\n\ngo 1.22\n")
    cart = write(tmp_path, "src/shop/cart.go", "package shop\n\n// cafe\n")
    write(tmp_path, "src/billing/invoice.go", "package billing\n")
    write_config(tmp_path, source_roots=["src"])
    write(tmp_path, "docs/components/shop.md", _component("shop", "src/shop/**", "billing"))
    write(tmp_path, "docs/components/billing.md", _component("billing", "src/billing/**"))

    assert [f.code for f in run_check(DependencyCheck, tmp_path)] == [
        "import-deps/hallucinated-dependency"
    ]

    cart.write_bytes(b"package shop\n\n// caf\xe9\n")

    assert run_check(DependencyCheck, tmp_path) == []


def test_two_files_of_one_package_owned_by_two_docs_are_related_with_no_import(
    tmp_path: Path,
) -> None:
    write(tmp_path, "go.mod", "module example.com/shop\n\ngo 1.22\n")
    write(
        tmp_path,
        "desk/checkout.go",
        "package desk\n\nfunc CheckOut() int {\n\treturn lateFine() + 1\n}\n",
    )
    write(tmp_path, "desk/ledger.go", "package desk\n\nfunc lateFine() int {\n\treturn 25\n}\n")
    write_config(tmp_path, source_roots=["desk"])
    write(
        tmp_path,
        "docs/components/checkout.md",
        "---\nid: checkout\ntitle: Checkout\nstatus: stable\nsummary: Lends an item.\n"
        "describes:\n  - desk/checkout.go\ndepends_on:\n  - ledger\n---\n\n# Checkout\n\nLends.\n",
    )
    write(
        tmp_path,
        "docs/components/ledger.md",
        "---\nid: ledger\ntitle: Ledger\nstatus: stable\nsummary: Keeps the fines.\n"
        "describes:\n  - desk/ledger.go\n---\n\n# Ledger\n\nKeeps fines.\n",
    )

    assert run_check(DependencyCheck, tmp_path) == []


def test_context_for_the_desk_file_names_its_package_test_for_the_import(
    fixture_repo: Callable[[str], Path],
) -> None:
    root = fixture_repo("go-library")

    [result] = invoke_json(root, "context", "internal/desk/desk.go")["results"]

    assert result["tests"] == ["internal/desk/desk_test.go"]
    assert result["test_reasons"] == {
        "internal/desk/desk_test.go": ["imports internal/desk/desk.go"]
    }


def test_context_for_the_policy_file_names_its_package_test_for_the_import(
    fixture_repo: Callable[[str], Path],
) -> None:
    root = fixture_repo("go-library")

    [result] = invoke_json(root, "context", "internal/policy/policy.go")["results"]

    assert result["tests"] == ["internal/policy/policy_test.go"]
    assert result["test_reasons"] == {
        "internal/policy/policy_test.go": ["imports internal/policy/policy.go"]
    }


def test_suggest_offers_the_test_that_calls_late_fee_for_the_guide_sentence(
    fixture_repo: Callable[[str], Path],
) -> None:
    root = fixture_repo("go-library")

    assert invoke_json(root, "anchors", "--suggest", "--doc", "docs/guides/lending.md") == {
        "version": 1,
        "unbound": [],
        "resolved": [
            {
                "path": "docs/guides/lending.md",
                "line": 11,
                "name": "LateFee",
                "definition": {"path": "internal/policy/policy.go", "line": 10},
                "tests": [
                    {
                        "path": "internal/policy/policy_test.go",
                        "line": 9,
                        "symbol": "TestLateFee",
                        "marker": "<!-- anchor: internal/policy/policy_test.go#TestLateFee -->",
                    }
                ],
            }
        ],
    }


def test_editing_late_fee_queues_the_guide_sentence_that_names_it(
    fixture_repo: Callable[[str], Path],
) -> None:
    root = fixture_repo("go-library")
    seed_repo(root, "the fixture as it stands", when=SEEDED)
    replace_text(root, "internal/policy/policy.go", "return days * 25", "return days * 30")

    items = invoke_json(root, "list", "review", "--changed")["items"]

    [item] = [item for item in items if "names-changed-code" in item["markers"]]
    assert item["path"] == "docs/guides/lending.md"


def _pinned_desk_doc(root: Path) -> None:
    doc = "docs/components/desk.md"
    write(root, doc, (root / doc).read_text(encoding="utf-8") + ANCHORED_PARAGRAPH)
    code, output = invoke(root, "anchors", "--re-pin", "--doc", doc)
    assert code == 0, output
    assert run_check(ClaimAnchorCheck, root) == []


def test_a_comment_inside_a_pinned_method_moves_no_pin(
    fixture_repo: Callable[[str], Path],
) -> None:
    root = fixture_repo("go-library")
    _pinned_desk_doc(root)

    replace_text(
        root, "internal/desk/desk.go", "\td.loans++\n", "\t// count the loan first\n\td.loans++\n"
    )

    assert run_check(ClaimAnchorCheck, root) == []


def test_an_edit_to_a_pinned_methods_body_is_pinned_drift(
    fixture_repo: Callable[[str], Path],
) -> None:
    root = fixture_repo("go-library")
    _pinned_desk_doc(root)

    replace_text(
        root,
        "internal/desk/desk.go",
        'fmt.Errorf("no item for %s", patron)',
        'fmt.Errorf("no item for patron %s", patron)',
    )

    [finding] = run_check(ClaimAnchorCheck, root)
    assert finding.code == "claim-anchor/pinned-drift"


def _component(doc_id: str, describes: str, depends_on: str | None = None) -> str:
    needs = f"depends_on:\n  - {depends_on}\n" if depends_on else ""
    return (
        f"---\nid: {doc_id}\ntitle: {doc_id.title()}\nstatus: stable\n"
        f"summary: The {doc_id} component.\ndescribes:\n  - {describes}\n{needs}---\n\n"
        f"# {doc_id.title()}\n\nThe {doc_id} component.\n"
    )


def test_a_go_file_places_every_import_only_under_a_go_mod(tmp_path: Path) -> None:
    under = write(tmp_path, "lib/desk/desk.go", "package desk\n")
    loose = write(tmp_path, "loose/desk.go", "package desk\n")
    write(tmp_path, "lib/go.mod", "module example.com/lib\n\ngo 1.22\n")

    assert _reading(under).places_every_import(under)
    assert not _reading(loose).places_every_import(loose)
    assert not _reading(under, "package desk\n\nfunc (").places_every_import(under)


def test_a_true_dependency_is_not_reported_where_no_go_mod_says_where_imports_lead(
    fixture_repo: Callable[[str], Path],
) -> None:
    """With its `go.mod` gone the library's imports cannot be placed, so a missing import
    proves nothing: neither the dependency its code has nor the one it has not is judged."""
    root = fixture_repo("go-library")
    (root / "go.mod").unlink()

    assert run_check(DependencyCheck, root) == []


def test_an_import_of_another_module_the_repository_declares_is_placed(tmp_path: Path) -> None:
    """The server only requires the api module: no `replace` line and no `go.work` says the
    module is next door, and its `go.mod` under a source root does."""
    write(tmp_path, "api/go.mod", "module example.com/api\n\ngo 1.22\n")
    write(tmp_path, "api/api.go", "package api\n\nfunc Version() int {\n\treturn 1\n}\n")
    write(
        tmp_path,
        "server/go.mod",
        "module example.com/server\n\ngo 1.22\n\nrequire example.com/api v1.0.0\n",
    )
    main = write(
        tmp_path,
        "server/main.go",
        'package main\n\nimport "example.com/api"\n\nfunc main() {\n\t_ = api.Version()\n}\n',
    )
    write_config(tmp_path, source_roots=["api", "server"])
    write(tmp_path, "docs/components/api.md", _component("api", "api/**"))
    write(tmp_path, "docs/components/server.md", _component("server", "server/**", "api"))
    roots = [tmp_path / "api", tmp_path / "server"]

    files = _reading(main).files("example.com/api", main, roots)

    assert _relative(files, tmp_path) == ["api/api.go"]
    assert run_check(DependencyCheck, tmp_path) == []


def _server_requiring_api(root: Path, *homes: str) -> Path:
    """A server module that requires `example.com/api`, which each of `homes` declares,
    under the one source root `.`; the `api` doc owns the first of them."""
    for home in homes:
        write(root, f"{home}/go.mod", "module example.com/api\n\ngo 1.22\n")
        write(root, f"{home}/api.go", "package api\n\nfunc Version() int {\n\treturn 1\n}\n")
    write(
        root,
        "server/go.mod",
        "module example.com/server\n\ngo 1.22\n\nrequire example.com/api v1.0.0\n",
    )
    main = write(
        root,
        "server/main.go",
        'package main\n\nimport "example.com/api"\n\nfunc main() {\n\t_ = api.Version()\n}\n',
    )
    write_config(root, source_roots=["."])
    write(root, "docs/components/api.md", _component("api", f"{homes[0]}/**"))
    write(root, "docs/components/server.md", _component("server", "server/**", "api"))
    return main


def test_a_module_is_found_among_the_source_files_whatever_its_directory_is_called(
    tmp_path: Path,
) -> None:
    """The `go` tool leaves `_shared` out of `./...`, and a module there is a module still:
    the run's own listing of the source root holds its `go.mod`."""
    main = _server_requiring_api(tmp_path, "_shared")
    tree = load_graph(tmp_path).source
    reading = tree.reading(main)
    assert reading is not None

    files = reading.files("example.com/api", main, [tmp_path])

    assert _relative(files, tmp_path) == ["_shared/api.go"]
    assert run_check(DependencyCheck, tmp_path) == []


def test_a_module_two_directories_declare_is_looked_for_in_both(tmp_path: Path) -> None:
    """Nothing says which copy the server means, so its import may load either, and the
    dependency on the doc that owns one of them is backed whichever the walk meets first."""
    main = _server_requiring_api(tmp_path, "services/api", "legacy/api")
    tree = load_graph(tmp_path).source
    reading = tree.reading(main)
    assert reading is not None

    files = reading.files("example.com/api", main, [tmp_path])

    assert _relative(files, tmp_path) == ["legacy/api/api.go", "services/api/api.go"]
    assert run_check(DependencyCheck, tmp_path) == []


def test_a_file_names_its_own_module_and_not_a_copy_of_it(tmp_path: Path) -> None:
    _server_requiring_api(tmp_path, "services/api", "legacy/api")
    inside = write(
        tmp_path,
        "services/api/sub/sub.go",
        'package sub\n\nimport "example.com/api"\n\nvar V = api.Version()\n',
    )
    tree = load_graph(tmp_path).source
    reading = tree.reading(inside)
    assert reading is not None

    files = reading.files("example.com/api", inside, [tmp_path])

    assert _relative(files, tmp_path) == ["services/api/api.go"]


def test_a_module_outside_what_the_source_walk_lists_is_not_found(tmp_path: Path) -> None:
    main = _server_requiring_api(tmp_path, "services/api")
    write(tmp_path, ".gitignore", "node_modules/\n")
    write(tmp_path, "node_modules/pkg/go.mod", "module example.com/apiary\n")
    write(tmp_path, "node_modules/pkg/apiary.go", "package apiary\n")
    tree = load_graph(tmp_path).source
    reading = tree.reading(main)
    assert reading is not None

    assert reading.files("example.com/apiary", main, [tmp_path]) == []


def test_the_fields_of_a_variable_of_an_unnamed_struct_type_are_not_definitions() -> None:
    """`Port` is a field of the value of `Config`, which no path names: it is not a
    variable at the top of the file."""
    text = "package a\n\nvar Config struct {\n\tPort int\n\tHost string\n}\n"

    assert [(d.symbol, d.kind, d.reachable) for d in _reading(SAMPLE, text).definitions()] == [
        ("Config", "variable", True)
    ]


def test_a_function_named_test_that_takes_no_testing_t_is_no_test() -> None:
    text = (
        'package desk\n\nimport "testing"\n\n'
        "func TestConnection() bool {\n\treturn true\n}\n\n"
        "func TestTwo(t *testing.T, n int) {}\n\n"
        "func TestBench(b *testing.B) {}\n\n"
        "func TestOpen(t *testing.T) {}\n"
    )

    assert [d.symbol for d in _reading(SAMPLE, text).tests()] == ["TestOpen"]


def test_a_statement_reads_the_same_ended_by_a_semicolon_or_a_line_break() -> None:
    one_line = "package a\n\nfunc f() int {\n\tx := 1; y := 2\n\treturn x + y\n}\n"
    two_lines = "package a\n\nfunc f() int {\n\tx := 1\n\ty := 2\n\treturn x + y\n}\n"

    assert _reading(SAMPLE, one_line).canonical("f") == _reading(SAMPLE, two_lines).canonical("f")


def test_a_module_is_found_by_its_go_files_where_the_walk_lists_no_go_mod(
    tmp_path: Path,
) -> None:
    """`source_includes` keeps only Go files, so the walk lists no `go.mod`. The api
    module is found by the `go.mod` above its Go file all the same."""
    main = _server_requiring_api(tmp_path, "services/api")
    write_config(tmp_path, source_roots=["."], extra='source_includes = ["**/*.go"]\n')
    tree = load_graph(tmp_path).source
    assert not [path for path, _ in tree.files if path.name == "go.mod"]
    reading = tree.reading(main)
    assert reading is not None

    files = reading.files("example.com/api", main, [tmp_path])

    assert _relative(files, tmp_path) == ["services/api/api.go"]
    assert run_check(DependencyCheck, tmp_path) == []
