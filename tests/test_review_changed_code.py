"""Tests for the sentences `list review --changed` queues because the change touched code
they name, marked `names-changed-code`.

Each test copies the `names-changed-code` fixture, a ledger whose docs name its methods,
commands, options, environment variable and one of its files in code spans, commits it whole,
and changes the code without editing a doc. What the queue then holds was selected by the
code change alone.
"""

from __future__ import annotations

import datetime as _dt
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest

from .conftest import commit_all, git, invoke, invoke_json, replace_text, seed_repo

SEEDED = _dt.datetime(2024, 1, 1, 12, tzinfo=_dt.UTC)
LATER = _dt.datetime(2024, 2, 1, 12, tzinfo=_dt.UTC)

CORE = "src/ledger/core.py"
CLI = "src/ledger/cli.py"
DATES = "src/ledger/dates.py"
SERVER = "src/ledger/server.py"
COMPONENT = "docs/components/ledger.md"
USAGE = "docs/guides/usage.md"
DECISION = "docs/decisions/amounts-keep-their-order.md"
README = "README.md"
MARKER = "names-changed-code"

ADD_BODY = ("self.amounts.append(amount)", "self.amounts.insert(0, amount)")
TOTAL_BODY = ("return sum(self.amounts)", "return sum(self.amounts, 0)")
REPORT_BODY = ('f"total: {total}"', 'f"sum: {total}"')
REMOVE_METHOD = (
    "    def remove(self, index: int) -> None:\n"
    '        """Drop the amount at `index`."""\n'
    "        del self.amounts[index]\n"
    "\n"
)
NAMES_ADD = {(COMPONENT, "Ledger.add"), (DECISION, "Ledger.add"), (USAGE, CORE)}
NAMES_REPORT = {(USAGE, "ledger report"), (README, "ledger report"), (USAGE, "--plain")}


@pytest.fixture
def ledger(fixture_repo: Callable[[str], Path]) -> Path:
    """A copy of the fixture, committed whole at one fixed instant."""
    root = fixture_repo("names-changed-code")
    seed_repo(root, "the fixture as it stands", when=SEEDED)
    return root


def _queue(root: Path, *args: str) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = invoke_json(root, "list", "review", "--changed", *args)["items"]
    return items


def _named(items: list[dict[str, Any]]) -> set[tuple[str, str]]:
    """(doc, code span) for each span a queued sentence is asked about again."""
    return {
        (item["path"], code["span"])
        for item in items
        if MARKER in item["markers"]
        for code in item["changed_code"]
    }


def _changed_code(items: list[dict[str, Any]], path: str, span: str) -> dict[str, Any]:
    [code] = [
        code
        for item in items
        if item["path"] == path
        for code in item["changed_code"]
        if code["span"] == span
    ]
    return dict(code)


def test_an_edit_inside_a_function_queues_each_sentence_that_names_it(ledger: Path) -> None:
    replace_text(ledger, CORE, *ADD_BODY)

    items = _queue(ledger)

    assert _named(items) == NAMES_ADD
    [item] = [item for item in items if item["path"] == COMPONENT]
    assert item["markers"] == [MARKER]
    assert item["line"] == 16
    assert item["sentence"] == "`Ledger.add` enters an amount after every amount already there."
    assert item["changed_code"] == [
        {
            "span": "Ledger.add",
            "kind": "symbol",
            "identity": "add",
            "path": CORE,
            "line": 12,
            "removed": False,
        }
    ]
    assert item["references"][0]["defined_at"] == CORE


def test_a_decision_record_is_asked_about_its_decision_alone(ledger: Path) -> None:
    """The record names `Ledger.add` in its Decision and `Ledger.remove` in its Context."""
    replace_text(ledger, CORE, *ADD_BODY)
    replace_text(ledger, CORE, "del self.amounts[index]", "self.amounts.pop(index)")

    in_record = [item for item in _queue(ledger) if item["path"] == DECISION]

    assert [(item["line"], item["markers"]) for item in in_record] == [(21, [MARKER])]
    assert in_record[0]["sentence"].startswith("`Ledger.add` enters an amount last")


def test_renaming_a_method_queues_the_sentence_that_names_the_old_name(ledger: Path) -> None:
    """The requirement's second scenario. The old name is found in the merge base's text,
    because the working tree no longer defines it."""
    replace_text(ledger, CORE, "def remove(", "def delete(")

    items = _queue(ledger)

    assert _named(items) == {(COMPONENT, "Ledger.remove"), (USAGE, CORE)}
    [item] = [item for item in items if item["path"] == COMPONENT]
    assert item["sentence"] == "`Ledger.remove` drops one amount and keeps the others in order."
    assert item["references"] == []
    assert item["changed_code"] == [
        {
            "span": "Ledger.remove",
            "kind": "symbol",
            "identity": "remove",
            "path": CORE,
            "line": 14,
            "removed": True,
        }
    ]


def test_a_renamed_method_is_not_hidden_by_a_method_of_the_same_name_beside_it(
    ledger: Path,
) -> None:
    """With `Drawer.remove` in the same file, the span `Ledger.remove` pairs with it once
    `Ledger.remove` is gone. That is another definition, so the one the sentence named was
    still removed."""
    with (ledger / CORE).open("a", encoding="utf-8") as file:
        file.write(
            "\n\nclass Drawer:\n"
            '    """Coins, counted by hand."""\n\n'
            "    def remove(self, coins: int) -> None:\n"
            '        """Take `coins` out."""\n'
        )
    commit_all(ledger, "a drawer", when=LATER)
    replace_text(ledger, CORE, "def remove(self, index", "def delete(self, index")

    items = _queue(ledger)

    assert _named(items) == {(COMPONENT, "Ledger.remove"), (USAGE, CORE)}
    assert _changed_code(items, COMPONENT, "Ledger.remove")["removed"] is True


def test_a_name_a_second_definition_made_ambiguous_is_not_called_removed(ledger: Path) -> None:
    """`parse_amount()` pairs with nothing once two functions have that name, and the one it
    named is still in its file, untouched, so the change removed nothing."""
    replace_text(ledger, CORE, *TOTAL_BODY)
    with (ledger / CLI).open("a", encoding="utf-8") as file:
        file.write(
            '\n\ndef parse_amount(text: str) -> int:\n    """Not the ledger\'s."""\n    return 0\n'
        )

    assert _named(_queue(ledger)) == {(COMPONENT, "Ledger.total"), (USAGE, CORE)}


def test_deleting_a_method_queues_the_sentence_that_names_it(ledger: Path) -> None:
    replace_text(ledger, CORE, REMOVE_METHOD, "")

    items = _queue(ledger)

    assert _named(items) == {(COMPONENT, "Ledger.remove"), (USAGE, CORE)}
    assert _changed_code(items, COMPONENT, "Ledger.remove")["removed"] is True


def test_an_option_added_to_a_command_queues_the_sentences_that_name_the_command(
    ledger: Path,
) -> None:
    """The requirement's first and third scenarios: the usage guide and the README, which own
    no code, are asked about `ledger list`, and nothing is asked about the `report` command.
    `--limit` is asked about too, because the function that declares it changed."""
    replace_text(
        ledger,
        CLI,
        '    limit: Annotated[int, typer.Option("--limit")] = 0,\n',
        '    limit: Annotated[int, typer.Option("--limit")] = 0,\n'
        '    as_json: Annotated[bool, typer.Option("--json")] = False,\n',
    )

    items = _queue(ledger)

    assert _named(items) == {(USAGE, "ledger list"), (README, "ledger list"), (USAGE, "--limit")}
    assert _changed_code(items, USAGE, "ledger list") == {
        "span": "ledger list",
        "kind": "cli",
        "identity": "list",
        "path": CLI,
        "line": 14,
        "removed": False,
    }
    assert all(item["markers"] == [MARKER] for item in items)


def test_a_command_whose_declaring_line_changes_is_asked_about(ledger: Path) -> None:
    replace_text(ledger, CLI, "def list_amounts(", "def list_all(")

    items = _queue(ledger)

    assert _named(items) == {(USAGE, "ledger list"), (README, "ledger list"), (USAGE, "--limit")}
    assert _changed_code(items, README, "ledger list")["line"] == 12


def test_an_option_whose_declaring_line_changes_is_asked_about(ledger: Path) -> None:
    replace_text(
        ledger, CLI, 'typer.Option("--plain")', 'typer.Option("--plain", help="The bare number.")'
    )

    items = _queue(ledger)

    assert _named(items) == NAMES_REPORT
    assert _changed_code(items, USAGE, "--plain") == {
        "span": "--plain",
        "kind": "cli-options",
        "identity": "--plain",
        "path": CLI,
        "line": 23,
        "removed": False,
    }


def test_a_renamed_command_queues_the_sentences_that_name_the_old_command(ledger: Path) -> None:
    replace_text(ledger, CLI, "def report(", "def summary(")

    items = _queue(ledger)

    assert _named(items) == NAMES_REPORT
    assert _changed_code(items, USAGE, "ledger report") == {
        "span": "ledger report",
        "kind": "cli",
        "identity": "report",
        "path": CLI,
        "line": 22,
        "removed": True,
    }
    assert _changed_code(items, USAGE, "--plain")["removed"] is False


def test_an_environment_variable_whose_declaring_line_changes_is_asked_about(
    ledger: Path,
) -> None:
    replace_text(ledger, DATES, '"%Y-%m-%d")', '"%d.%m.%Y")')

    items = _queue(ledger)

    assert _named(items) == {(USAGE, "LEDGER_DATE_FORMAT")}
    assert _changed_code(items, USAGE, "LEDGER_DATE_FORMAT") == {
        "span": "LEDGER_DATE_FORMAT",
        "kind": "env-vars",
        "identity": "LEDGER_DATE_FORMAT",
        "path": DATES,
        "line": 8,
        "removed": False,
    }


def test_an_identity_with_no_declaring_line_is_paired_with_its_whole_file(ledger: Path) -> None:
    """The `env-vars` surface gives a file and no line, so the code a sentence names is the
    file, as it is when the queue marks code that changed after its doc."""
    replace_text(ledger, DATES, 'return "%m-%d"', 'return "%d.%m"')

    items = _queue(ledger)

    assert _named(items) == {(USAGE, "LEDGER_DATE_FORMAT")}
    assert _changed_code(items, USAGE, "LEDGER_DATE_FORMAT")["line"] == 13


def test_an_identity_declared_inside_another_function_is_its_own_function(ledger: Path) -> None:
    """Two tools are declared inside `build_server`. The function that declares one of them
    is the tool's own, the innermost that holds its declaring line, so an edit to the other
    tool, or to the function around both, asks nothing about it."""
    replace_text(ledger, SERVER, "return len(Ledger().amounts)", "return len(Ledger().amounts) + 0")

    assert _named(_queue(ledger)) == {(USAGE, "ledger_count")}

    replace_text(ledger, SERVER, 'server = FastMCP("ledger")', 'server = FastMCP("the ledger")')

    assert _named(_queue(ledger)) == {(USAGE, "ledger_count")}


def test_a_sentence_naming_a_whole_file_is_asked_about_on_any_edit_to_it(ledger: Path) -> None:
    replace_text(ledger, CORE, "return round(float(text) * 100)", "return int(float(text) * 100)")

    items = _queue(ledger)

    assert _named(items) == {(COMPONENT, "parse_amount()"), (USAGE, CORE)}
    assert _changed_code(items, USAGE, CORE) == {
        "span": CORE,
        "kind": "path",
        "identity": CORE,
        "path": CORE,
        "line": 25,
        "removed": False,
    }


def test_renaming_a_file_queues_the_sentence_that_names_it_and_not_what_moved_with_it(
    ledger: Path,
) -> None:
    """A rename git follows keeps each definition where the working tree has it, so the
    sentences naming `Ledger`'s methods are not asked about: no line of them changed."""
    git(ledger, "mv", CORE, "src/ledger/book.py")

    items = _queue(ledger)

    assert _named(items) == {(USAGE, CORE)}
    assert _changed_code(items, USAGE, CORE) == {
        "span": CORE,
        "kind": "path",
        "identity": CORE,
        "path": CORE,
        "line": None,
        "removed": True,
    }


def test_deleting_a_file_queues_every_sentence_that_names_it_or_its_code(ledger: Path) -> None:
    (ledger / CORE).unlink()

    items = _queue(ledger)

    assert _named(items) == {
        (USAGE, CORE),
        (COMPONENT, "Ledger.add"),
        (COMPONENT, "Ledger.remove"),
        (COMPONENT, "Ledger.total"),
        (COMPONENT, "parse_amount()"),
        (DECISION, "Ledger.add"),
    }
    assert all(code["removed"] for item in items for code in item["changed_code"])


def test_a_line_deleted_from_a_function_queues_the_sentences_that_name_it(ledger: Path) -> None:
    replace_text(ledger, CLI, '    """Print the total."""\n', "")

    assert _named(_queue(ledger)) == NAMES_REPORT


def test_a_sentence_the_change_wrote_keeps_one_item_and_carries_the_marker(ledger: Path) -> None:
    """How this meets the accepted RFC on the written sentences: `names-changed-code` items
    are about sentences the change did not write, and a sentence it did write stays its one
    `edited` item, which the marker joins."""
    replace_text(ledger, CORE, *ADD_BODY)
    replace_text(ledger, COMPONENT, "after every amount already", "before every amount already")

    items = _queue(ledger)

    about_add = [i for i in items if i["path"] == COMPONENT and "Ledger.add" in i["sentence"]]
    assert [item["markers"] for item in about_add] == [["edited", MARKER]]
    assert about_add[0]["was"] == "`Ledger.add` enters an amount after every amount already there."
    assert [code["line"] for code in about_add[0]["changed_code"]] == [12]
    assert _named(items) == NAMES_ADD


def test_a_sentence_on_a_changed_line_that_the_base_already_said_is_not_the_changes_own(
    ledger: Path,
) -> None:
    """A rewrapped paragraph is on changed lines and queues no `edited` item, so a sentence in
    it that names changed code is one the change did not write."""
    replace_text(ledger, CORE, *ADD_BODY)
    replace_text(
        ledger,
        COMPONENT,
        "`Ledger.add` enters an amount after every amount already there.",
        "`Ledger.add` enters an amount after\nevery amount already there.",
    )

    about_add = [
        i for i in _queue(ledger) if i["path"] == COMPONENT and "Ledger.add" in i["sentence"]
    ]

    assert [item["markers"] for item in about_add] == [[MARKER]]


def test_the_change_is_the_uncommitted_work_or_the_range_from_a_base(ledger: Path) -> None:
    git(ledger, "update-ref", "refs/remotes/origin/main", "HEAD")
    git(ledger, "checkout", "-qb", "feature")
    replace_text(ledger, CORE, *ADD_BODY)
    commit_all(ledger, "an amount is entered first", when=LATER)
    replace_text(ledger, CLI, *REPORT_BODY)

    assert _named(_queue(ledger)) == NAMES_REPORT
    assert _named(_queue(ledger, "--base-ref", "origin/main")) == NAMES_ADD | NAMES_REPORT
    assert _named(_queue(ledger, "--base-ref", "origin/main", "--committed-only")) == NAMES_ADD


def test_committed_only_reads_the_code_at_head(ledger: Path) -> None:
    """Uncommitted lines above a function move it in the working tree. The committed range
    is paired with the code `HEAD` holds, so the lines the commit changed still fall in the
    function it changed and not in the one the working tree has there."""
    git(ledger, "update-ref", "refs/remotes/origin/main", "HEAD")
    replace_text(ledger, CORE, *TOTAL_BODY)
    commit_all(ledger, "the total starts from zero", when=LATER)
    replace_text(
        ledger,
        CORE,
        "\n\nclass Ledger:",
        "\n\ndef cents(amount: float) -> int:\n"
        '    """`amount` in cents."""\n'
        "    return round(amount * 100)\n"
        "\n\nclass Ledger:",
    )

    committed = _queue(ledger, "--base-ref", "origin/main", "--committed-only")

    assert _named(committed) == {(COMPONENT, "Ledger.total"), (USAGE, CORE)}
    assert _changed_code(committed, COMPONENT, "Ledger.total")["line"] == 20


def test_a_committed_rename_is_read_from_the_merge_base(ledger: Path) -> None:
    git(ledger, "update-ref", "refs/remotes/origin/main", "HEAD")
    replace_text(ledger, CORE, "def remove(", "def delete(")
    commit_all(ledger, "remove is delete", when=LATER)

    for flags in (["--base-ref", "origin/main"], ["--base-ref", "origin/main", "--committed-only"]):
        items = _queue(ledger, *flags)
        assert _named(items) == {(COMPONENT, "Ledger.remove"), (USAGE, CORE)}, flags
        assert _changed_code(items, COMPONENT, "Ledger.remove")["removed"] is True
    assert _queue(ledger) == []


def test_a_change_to_docs_alone_queues_no_sentence_for_naming_code(ledger: Path) -> None:
    replace_text(ledger, USAGE, "oldest first", "newest last")

    items = _queue(ledger)

    assert [item["markers"] for item in items if item["path"] == USAGE] == [
        ["edited"],
        ["stale-summary"],
    ]
    assert _named(items) == set()


def test_without_a_change_no_item_carries_the_marker(ledger: Path) -> None:
    replace_text(ledger, CORE, *ADD_BODY)

    items = invoke_json(ledger, "list", "review", "--all")["items"]

    assert items
    assert all(item["markers"] == ["names-code"] for item in items)
    assert all(item["changed_code"] == [] for item in items)


def test_plain_output_names_the_code_and_where_the_change_touched_it(ledger: Path) -> None:
    from irminsul.listing.review import MARKER_MEANINGS

    replace_text(ledger, CORE, *ADD_BODY)
    replace_text(ledger, CORE, "def remove(", "def delete(")

    code, output = invoke(ledger, "list", "review", "--changed")

    assert code == 0
    assert (
        f"{COMPONENT}:16 ({MARKER})\n"
        "  `Ledger.add` enters an amount after every amount already there.\n"
        f"    `Ledger.add` -> symbol add ({CORE}:10-12)\n"
        f"    changed: symbol add at {CORE}:12\n"
    ) in output
    assert (
        f"{COMPONENT}:18 ({MARKER})\n"
        "  `Ledger.remove` drops one amount and keeps the others in order.\n"
        f"    removed: symbol remove, at {CORE}:14 before this change\n"
    ) in output
    lines = output.splitlines()
    legend = lines[lines.index("markers:") + 1 :]
    assert [line.split()[0] for line in legend] == [MARKER]
    assert MARKER_MEANINGS[MARKER] in legend[0]


def test_json_output_defines_the_marker_once(ledger: Path) -> None:
    from irminsul.listing.review import MARKER_MEANINGS

    replace_text(ledger, CORE, *ADD_BODY)

    report = invoke_json(ledger, "list", "review", "--changed")

    assert report["markers"] == {MARKER: MARKER_MEANINGS[MARKER]}
    assert report["total"] == report["shown"] == 3


def test_the_doc_filter_keeps_the_sentences_of_that_doc(ledger: Path) -> None:
    replace_text(ledger, CORE, *ADD_BODY)

    assert _named(_queue(ledger, "--doc", USAGE)) == {(USAGE, CORE)}
