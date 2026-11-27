"""Python's reader answers the five questions of the language interface from `ast`."""

from __future__ import annotations

from pathlib import Path

import pytest

import irminsul
from irminsul.inventory.base import SourceReader
from irminsul.languages import PYTHON_PROFILE, READERS, languages_read, reader_for
from irminsul.languages.python_reader import PYTHON_READER, PythonReading
from irminsul.languages.reader import Definition, imported_files

LEDGER = """\
import os
import loans.policy
import loans.fees as fees
from loans import rates as r, caps
from . import sibling
from ..shared.util import clamp as limit
from loans.everything import *

LIMIT, SPARE = 5, 6


@register
@register.with_args(1)
def late_fee(days):
    import loans.extra
    total = fees.base(days) + r.daily
    return limit(total, LIMIT)


class Ledger:
    RATE = 2

    def remove(self, entry):
        return entry

    class Entry:
        def close(self):
            pass


if os.environ:
    def hidden():
        pass

    def test_in_a_block():
        pass


def outer():
    def inner():
        pass
    local_name = 1
    return inner


def test_late_fee_caps():
    assert late_fee(3) == LIMIT


class TestLedger:
    def test_remove(self):
        pass

    def helper(self):
        pass
"""


def _read(text: str = LEDGER) -> PythonReading:
    return PYTHON_READER.read(text)


def _named(reading: PythonReading, symbol: str) -> Definition:
    return next(d for d in reading.definitions() if d.symbol == symbol)


def test_the_python_profile_names_its_reader() -> None:
    assert PYTHON_PROFILE.reader == "python"
    assert READERS["python"] is PYTHON_READER
    assert reader_for("src/loans/ledger.py") is PYTHON_READER
    assert reader_for(Path("src") / "ledger.py") is PYTHON_READER
    assert reader_for("src/fees.ts") is None
    assert languages_read() == ["python"]


def test_a_definition_carries_its_name_holder_and_lines() -> None:
    reading = _read()

    fee = _named(reading, "late_fee")
    assert (fee.kind, fee.first, fee.line, fee.end) == ("function", 12, 14, 17)
    assert fee.holder is None and fee.reachable

    remove = _named(reading, "Ledger.remove")
    assert (remove.kind, remove.holder, remove.line, remove.end) == ("function", "Ledger", 23, 24)

    entry = _named(reading, "Ledger.Entry")
    assert (entry.kind, entry.holder, entry.line, entry.end) == ("type", "Ledger", 26, 28)
    close = _named(reading, "Ledger.Entry.close")
    assert (close.holder, close.line) == ("Ledger.Entry", 27)


def test_an_assignment_outside_a_function_is_a_definition_and_a_local_is_not() -> None:
    reading = _read()

    assert [(d.symbol, d.kind, d.line) for d in reading.definitions() if d.kind == "variable"] == [
        ("LIMIT", "variable", 9),
        ("SPARE", "variable", 9),
        ("Ledger.RATE", "variable", 21),
    ]


def test_a_definition_no_dotted_path_reaches_says_so() -> None:
    reading = _read()

    hidden = _named(reading, "hidden")
    inner = _named(reading, "outer.inner")
    assert not hidden.reachable and hidden.holder is None
    assert not inner.reachable and inner.holder is None


def test_imports_say_what_they_bind_and_where() -> None:
    reading = _read()
    seen = [
        (i.source, [(n.local, n.name, n.reached_as, n.source) for n in i.names], i.scope)
        for i in reading.imports()
    ]

    assert seen == [
        ("os", [("os", None, "os", None)], ()),
        ("loans.policy", [("loans", None, "loans.policy", None)], ()),
        ("loans.fees", [("fees", None, "fees", None)], ()),
        ("loans", [("r", "rates", "r", "loans.rates"), ("caps", "caps", "caps", "loans.caps")], ()),
        (".", [("sibling", "sibling", "sibling", ".sibling")], ()),
        ("..shared.util", [("limit", "clamp", "limit", "..shared.util.clamp")], ()),
        ("loans.everything", [("*", "*", "*", None)], ()),
        ("loans.extra", [("loans", None, "loans.extra", None)], ("late_fee",)),
    ]


def test_an_import_resolves_to_the_files_its_module_may_be(tmp_path: Path) -> None:
    reading = _read()
    src = tmp_path / "src"
    importer = src / "loans" / "book" / "ledger.py"

    assert reading.files("loans.fees", importer, [src]) == [
        src / "loans" / "fees.py",
        src / "loans" / "fees" / "__init__.py",
    ]
    assert reading.files(".", importer, [src]) == [src / "loans" / "book" / "__init__.py"]
    assert reading.files("..shared.util", importer, [src]) == [
        src / "loans" / "shared" / "util.py",
        src / "loans" / "shared" / "util" / "__init__.py",
    ]
    files = imported_files(reading, importer, [src])
    assert src / "loans" / "rates.py" in files
    assert src / "loans" / "extra.py" in files


def test_a_body_refers_to_the_names_it_reads_and_binds_its_own() -> None:
    reading = _read()

    refs = reading.references(_named(reading, "late_fee"))

    assert {"fees", "r", "limit", "LIMIT"} <= refs.names
    assert ("fees", "base") in refs.attributes and ("r", "daily") in refs.attributes
    assert refs.bound == {"days", "total"}
    assert [i.source for i in refs.imports] == ["loans.extra"]


def test_canonical_text_ignores_comments_and_layout_and_not_the_code() -> None:
    reading = _read()
    reformatted = _read(
        LEDGER.replace(
            "    total = fees.base(days) + r.daily\n",
            "    # the fee and the rate\n    total = (fees.base(days)\n             + r.daily)\n",
        )
    )
    changed = _read(LEDGER.replace("r.daily", "r.weekly"))

    assert reading.canonical("late_fee") == reformatted.canonical("late_fee")
    assert reading.canonical("late_fee") != changed.canonical("late_fee")
    assert reading.canonical("Ledger.remove") == changed.canonical("Ledger.remove")
    assert reading.canonical("LIMIT") == reading.canonical("SPARE")
    assert reading.canonical() is not None and reading.canonical() != changed.canonical()


def test_canonical_text_reaches_only_what_an_anchor_names() -> None:
    reading = _read()

    assert reading.canonical("Ledger.Entry.close") is not None
    assert reading.canonical("hidden") is None
    assert reading.canonical("outer.inner") is None
    assert reading.canonical("LIMIT.real") is None
    assert reading.canonical("missing") is None


def test_tests_are_functions_named_test_that_an_anchor_reaches() -> None:
    reading = _read()

    assert [d.symbol for d in reading.tests()] == ["test_late_fee_caps", "TestLedger.test_remove"]


def test_a_file_that_does_not_parse_answers_nothing_and_says_so(tmp_path: Path) -> None:
    reading = _read("def late_fee(:\n    return 1\n")

    assert not reading.parsed
    assert reading.definitions() == ()
    assert reading.imports() == ()
    assert reading.tests() == ()
    assert reading.canonical() is None and reading.canonical("late_fee") is None
    assert imported_files(reading, tmp_path / "a.py", [tmp_path]) == []


@pytest.mark.xfail(
    strict=True,
    raises=AssertionError,
    reason="BACKLOG.md python-reader-lists-a-trys-else-before-its-handlers",
)
def test_what_a_try_statement_holds_is_listed_in_the_order_the_file_holds_it() -> None:
    reading = _read(
        "try:\n    import a\nexcept ImportError:\n    import b\n"
        "else:\n    import c\nfinally:\n    import d\n"
    )

    assert [found.line for found in reading.imports()] == [2, 4, 6, 8]


def test_only_the_reader_and_the_framework_extractors_import_pythons_parser() -> None:
    package = Path(irminsul.__file__).parent

    importing = {
        path.relative_to(package).as_posix()
        for path in package.rglob("*.py")
        if any(found.source == "ast" for found in _read(path.read_text("utf-8")).imports())
    }

    assert importing == {
        "checks/glossary.py",
        "inventory/cli_options.py",
        "inventory/cli_typer.py",
        "inventory/http_fastapi.py",
        "inventory/mcp.py",
        "languages/python_reader.py",
    }


def test_a_source_reader_keeps_one_reading_of_a_file_and_shares_its_parse(tmp_path: Path) -> None:
    path = tmp_path / "ledger.py"
    path.write_text(LEDGER, encoding="utf-8")
    source = SourceReader()

    on_disk = source.reading(path)

    assert on_disk is not None and on_disk is source.reading(path)
    assert on_disk.definitions() == _read().definitions()
    assert on_disk.canonical("Ledger") == _read().canonical("Ledger")
    assert source.reading(tmp_path / "fees.ts") is None
    assert source.module(path) is not None
    assert isinstance(on_disk, PythonReading) and source.module(path) is on_disk.module
