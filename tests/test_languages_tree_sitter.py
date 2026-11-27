"""The readers of TypeScript, Go and Rust answer the language interface through tree-sitter,
and the features that ask it reach their files with no word about a language."""

from __future__ import annotations

import datetime as _dt
from pathlib import Path

import pytest
import tree_sitter_go

from irminsul import languages
from irminsul.checks.dependency_check import DependencyCheck
from irminsul.code_references import CodeResolver
from irminsul.config import load
from irminsul.languages import READERS, reader_for
from irminsul.languages.base import LanguageProfile
from irminsul.languages.reader import Definition
from irminsul.languages.tree_sitter_reader import TreeSitterReader
from irminsul.source_tree import SourceTree

from .conftest import (
    invoke_json,
    replace_text,
    run_check,
    seed_repo,
    write,
    write_config,
    write_doc,
)

SEEDED = _dt.datetime(2024, 1, 1, 12, tzinfo=_dt.UTC)

FEES_TS = """\
import { rates } from "./rates";
export function lateFee(days: number): number {
  return Math.min(days * rates.daily, 500);
}
"""

DESK_GO = """\
package desk

// Desk lends.
type Desk struct{ open bool }

// CheckOut lends one item.
func (d *Desk) CheckOut(id string) string { return id }
"""


def _named(path: str, text: str, symbol: str) -> Definition:
    reader = reader_for(path)
    assert reader is not None
    return next(d for d in reader.read(text).definitions() if d.symbol == symbol)


def test_each_language_names_its_reader_and_a_dialect_by_suffix() -> None:
    assert reader_for("src/fees.ts") is READERS["typescript"]
    assert reader_for("src/fees.mts") is READERS["typescript"]
    for suffix in (".tsx", ".js", ".jsx", ".mjs", ".cjs"):
        assert reader_for(f"src/fees{suffix}") is READERS["tsx"]
    assert reader_for("desk.go") is READERS["go"]
    assert reader_for("src/lib.rs") is READERS["rust"]
    assert reader_for("src/fees.rb") is None


def test_a_typescript_function_is_found_with_its_lines() -> None:
    fee = _named("src/fees.ts", FEES_TS, "lateFee")

    assert (fee.kind, fee.first, fee.line, fee.end) == ("function", 2, 2, 4)


def test_a_go_method_is_found_on_its_line_and_held_by_its_receiver() -> None:
    method = _named("desk.go", DESK_GO, "Desk.CheckOut")

    assert (method.name, method.holder, method.line) == ("CheckOut", "Desk", 7)


def test_a_change_to_a_typescript_function_queues_the_sentence_that_names_it(
    tmp_path: Path,
) -> None:
    write_config(tmp_path, source_roots=["src"])
    write(tmp_path, "src/fees.ts", FEES_TS)
    write(tmp_path, "src/rates.ts", "export const rates = { daily: 25 };\n")
    write_doc(
        tmp_path,
        "docs/guides/fees.md",
        doc_id="fees",
        body="The fine `lateFee()` charges stops growing at 5 dollars.\n",
    )
    seed_repo(tmp_path, when=SEEDED)
    replace_text(tmp_path, "src/fees.ts", "days * rates.daily", "days * rates.daily * 2")

    items = invoke_json(tmp_path, "list", "review", "--changed")["items"]

    [item] = [item for item in items if "names-changed-code" in item["markers"]]
    assert item["path"] == "docs/guides/fees.md"
    assert item["changed_code"] == [
        {
            "span": "lateFee()",
            "identity": "lateFee",
            "path": "src/fees.ts",
            "line": 3,
            "removed": False,
        }
    ]


def test_a_language_is_added_by_a_profile_a_grammar_and_a_query_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A made-up language with files in `.gox`, read through Go's grammar and a query file of
    one pattern: no check and no feature is told about it."""
    queries = "(function_declaration name: (identifier) @name) @definition.function\n"
    monkeypatch.setitem(
        languages.LANGUAGE_REGISTRY,
        "gox",
        LanguageProfile(
            name="gox",
            source_root_candidates=(),
            schema_leak_patterns=(),
            suffixes=(".gox",),
            reader="gox",
        ),
    )
    monkeypatch.setitem(
        languages.READERS, "gox", TreeSitterReader(tree_sitter_go.language, lambda: queries)
    )
    write_config(tmp_path, source_roots=["src"])
    write(
        tmp_path,
        "src/desk.gox",
        "package desk\n\nfunc RenewLoan(id string) string {\n\treturn id\n}\n",
    )

    resolver = CodeResolver(SourceTree(tmp_path, load(tmp_path / "irminsul.toml")))

    [found] = resolver.resolve("RenewLoan()")
    assert (found.kind, found.identity, found.defined_at, found.line, found.line_end) == (
        "symbol",
        "RenewLoan",
        "src/desk.gox",
        3,
        5,
    )


def _component(doc_id: str, describes: str, depends_on: str | None = None) -> str:
    needs = f"depends_on:\n  - {depends_on}\n" if depends_on else ""
    return (
        f"---\nid: {doc_id}\ntitle: {doc_id.title()}\nstatus: stable\n"
        f"summary: The {doc_id} component.\ndescribes:\n  - {describes}\n{needs}---\n\n"
        f"# {doc_id.title()}\n\nThe {doc_id} component.\n"
    )


def test_a_missing_import_denies_a_dependency_only_where_every_shared_import_is_placed(
    tmp_path: Path,
) -> None:
    """Two components of Python alone, with no import between them, are unrelated, and the
    `depends_on` is reported. Give each a JavaScript file and one of those could carry the
    dependency through a path alias the reader does not follow, so it is no longer judged."""
    write(tmp_path, "src/shop/cart.py", "TOTAL = 0\n")
    write(tmp_path, "src/billing/invoice.py", "RATE = 2\n")
    write_config(tmp_path, source_roots=["src"])
    write(tmp_path, "docs/components/shop.md", _component("shop", "src/shop/**", "billing"))
    write(tmp_path, "docs/components/billing.md", _component("billing", "src/billing/**"))

    assert [f.code for f in run_check(DependencyCheck, tmp_path)] == [
        "import-deps/hallucinated-dependency"
    ]

    write(tmp_path, "src/shop/cart.js", 'import { rate } from "@billing/rate";\n')
    write(tmp_path, "src/billing/rate.js", "export const rate = 2;\n")

    assert run_check(DependencyCheck, tmp_path) == []
