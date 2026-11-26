"""Tests for the sentences `list review --changed` queues because the change touched a
function or class they name, marked `names-changed-code`.

Each test copies the `names-changed-code` fixture, a ledger whose docs name its class, its
methods and functions, its commands, options, environment variable, one of its tools and two
of its files in code spans, commits it whole, and changes the code without editing a doc.
What the queue then holds was selected by the code change alone.
"""

from __future__ import annotations

import datetime as _dt
import json
import re
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest
from typer.testing import CliRunner

from irminsul.cli import app

from .conftest import commit_all, git, invoke, invoke_json, replace_text, seed_repo

SEEDED = _dt.datetime(2024, 1, 1, 12, tzinfo=_dt.UTC)
LATER = _dt.datetime(2024, 2, 1, 12, tzinfo=_dt.UTC)

CORE = "src/ledger/core.py"
CLI = "src/ledger/cli.py"
DATES = "src/ledger/dates.py"
FEES = "src/ledger/fees.py"
SERVER = "src/ledger/server.py"
COMPONENT = "docs/components/ledger.md"
USAGE = "docs/guides/usage.md"
DECISION = "docs/decisions/amounts-keep-their-order.md"
README = "README.md"
MARKER = "names-changed-code"

ADD_BODY = ("self.amounts.append(amount)", "self.amounts.insert(0, amount)")
TOTAL_BODY = ("return sum(self.amounts)", "return sum(self.amounts, 0)")
FEE_BODY = ("min(days * 50, 500)", "min(days * 75, 500)")
REMOVE_METHOD = (
    "    def remove(self, index: int) -> None:\n"
    '        """Drop the amount at `index`."""\n'
    "        del self.amounts[index]\n"
    "\n"
)
#: The README names the class, whose range every method lies in.
NAMES_LEDGER = (README, "Ledger")
NAMES_ADD = {(COMPONENT, "Ledger.add"), (DECISION, "Ledger.add"), NAMES_LEDGER}
NAMES_REMOVE = {(COMPONENT, "Ledger.remove"), NAMES_LEDGER}
NAMES_TOTAL = {(COMPONENT, "Ledger.total"), NAMES_LEDGER}
NAMES_FEE = {(USAGE, "late_fee()")}


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
        {"span": "Ledger.add", "identity": "add", "path": CORE, "line": 12, "removed": False}
    ]
    assert item["references"][0]["defined_at"] == CORE


def test_a_function_whose_body_changed_queues_the_guide_that_names_it(ledger: Path) -> None:
    """The requirement's second scenario: the usage guide owns no code and names `late_fee()`."""
    replace_text(ledger, FEES, *FEE_BODY)

    items = _queue(ledger)

    assert _named(items) == NAMES_FEE
    [item] = items
    assert item["markers"] == [MARKER]
    assert item["sentence"] == "`late_fee()` charges fifty cents for each day a payment is late."
    assert item["changed_code"] == [
        {"span": "late_fee()", "identity": "late_fee", "path": FEES, "line": 6, "removed": False}
    ]


def test_a_sentence_naming_a_function_the_change_left_alone_is_not_queued(ledger: Path) -> None:
    """The requirement's third scenario: `due_day()` is defined beside `late_fee` and named in
    the next sentence of the same guide."""
    replace_text(ledger, FEES, *FEE_BODY)

    assert [item["sentence"] for item in _queue(ledger) if "due_day()" in item["sentence"]] == []


def test_a_function_moved_in_its_file_with_its_lines_unchanged_is_not_asked_about(
    ledger: Path,
) -> None:
    """A definition is touched when its lines are not the ones it had at the base, wherever
    in the file they now are."""
    function = (
        "\n\ndef parse_amount(text: str) -> int:\n"
        '    """The cents `text` names, such as 1250 for "12.50"."""\n'
        "    return round(float(text) * 100)\n"
    )
    replace_text(ledger, CORE, function, "")
    replace_text(ledger, CORE, "\n\nclass Ledger:", f"{function}\n\nclass Ledger:")

    assert _queue(ledger) == []


def test_deleting_the_function_below_one_does_not_touch_the_one_above(ledger: Path) -> None:
    """The requirement's scenario "The function below is deleted": git files a hunk that only
    deletes under the line before it, here the last line of `late_fee`. The deleted lines lay
    in `due_day` alone, so that is the sentence asked, and the one naming `late_fee()` is not."""
    replace_text(
        ledger,
        FEES,
        "\n\ndef due_day(entered: int) -> int:\n"
        '    """The day a payment entered on day `entered` is due."""\n'
        "    return entered + 30\n",
        "",
    )

    items = _queue(ledger)

    assert _named(items) == {(USAGE, "due_day()")}
    assert _changed_code(items, USAGE, "due_day()") == {
        "span": "due_day()",
        "identity": "due_day",
        "path": FEES,
        "line": 9,
        "removed": True,
    }


def test_deleting_the_last_line_of_a_function_queues_the_sentence_that_names_it(
    ledger: Path,
) -> None:
    """The deleted line lay in the function's range at the base, which is where a deletion
    is read; the line reported is the function's last where the change ends."""
    replace_text(ledger, FEES, "    return min(days * 50, 500)\n", "")

    items = _queue(ledger)

    assert _named(items) == NAMES_FEE
    assert _changed_code(items, USAGE, "late_fee()")["line"] == 5


def test_an_edited_function_is_asked_about_though_a_second_one_took_its_name(
    ledger: Path,
) -> None:
    """With a second `late_fee` in another file the span pairs with neither, so the changed
    lines are tested against the definition the name had at the base."""
    replace_text(ledger, FEES, *FEE_BODY)
    with (ledger / DATES).open("a", encoding="utf-8") as file:
        file.write('\n\ndef late_fee() -> int:\n    """Not the ledger\'s."""\n    return 0\n')

    items = _queue(ledger)

    assert _named(items) == NAMES_FEE
    [item] = items
    assert item["references"] == []
    assert item["changed_code"] == [
        {"span": "late_fee()", "identity": "late_fee", "path": FEES, "line": 6, "removed": False}
    ]


def test_a_file_that_no_longer_parses_changed_its_functions_and_removed_none(
    ledger: Path,
) -> None:
    """What the file defines cannot be read where the change ends, so each definition a
    sentence named at the base is reported as changed, with no line, as an untracked file's
    are."""
    replace_text(
        ledger, FEES, "def due_day(entered: int) -> int:", "def due_day(entered: int -> int:"
    )

    items = _queue(ledger)

    assert _named(items) == {(USAGE, "late_fee()"), (USAGE, "due_day()")}
    for span, identity in (("late_fee()", "late_fee"), ("due_day()", "due_day")):
        assert _changed_code(items, USAGE, span) == {
            "span": span,
            "identity": identity,
            "path": FEES,
            "line": None,
            "removed": False,
        }


def test_a_change_to_a_decorator_alone_queues_the_sentence_that_names_its_function(
    ledger: Path,
) -> None:
    """A definition is its decorators, its `def` or `class` line and its body, as an anchor
    reads it."""
    with (ledger / FEES).open("a", encoding="utf-8") as file:
        file.write(
            "\n\n@lru_cache(maxsize=1)\ndef flat_fee() -> int:\n"
            '    """The fee charged once a month."""\n    return 500\n'
        )
    with (ledger / USAGE).open("a", encoding="utf-8") as file:
        file.write("\n`flat_fee()` is charged once a month.\n")
    commit_all(ledger, "a flat fee", when=LATER)
    replace_text(ledger, FEES, "@lru_cache(maxsize=1)", "@lru_cache(maxsize=None)")

    items = _queue(ledger)

    assert _named(items) == {(USAGE, "flat_fee()")}
    assert _changed_code(items, USAGE, "flat_fee()") == {
        "span": "flat_fee()",
        "identity": "flat_fee",
        "path": FEES,
        "line": 14,
        "removed": False,
    }
    assert items[0]["references"][0]["line"] == 15


def test_a_class_is_touched_by_a_change_to_any_line_in_its_range(ledger: Path) -> None:
    replace_text(ledger, CORE, "self.amounts: list[int] = []", "self.amounts: list[int] = [0]")

    items = _queue(ledger)

    assert _named(items) == {NAMES_LEDGER}
    assert _changed_code(items, README, "Ledger") == {
        "span": "Ledger",
        "identity": "Ledger",
        "path": CORE,
        "line": 8,
        "removed": False,
    }


def test_a_decision_record_is_asked_about_its_decision_alone(ledger: Path) -> None:
    """The record names `Ledger.add` in its Decision and `Ledger.remove` in its Context."""
    replace_text(ledger, CORE, *ADD_BODY)
    replace_text(ledger, CORE, "del self.amounts[index]", "self.amounts.pop(index)")

    in_record = [item for item in _queue(ledger) if item["path"] == DECISION]

    assert [(item["line"], item["markers"]) for item in in_record] == [(21, [MARKER])]
    assert in_record[0]["sentence"].startswith("`Ledger.add` enters an amount last")


def test_renaming_a_method_queues_the_sentence_that_names_the_old_name(ledger: Path) -> None:
    """The requirement's first scenario. The old name is found in the merge base's text,
    because the working tree no longer defines it."""
    replace_text(ledger, CORE, "def remove(", "def delete(")

    items = _queue(ledger)

    assert _named(items) == NAMES_REMOVE
    [item] = [item for item in items if item["path"] == COMPONENT]
    assert item["markers"] == [MARKER]
    assert item["sentence"] == "`Ledger.remove` drops one amount and keeps the others in order."
    assert item["references"] == []
    assert item["changed_code"] == [
        {"span": "Ledger.remove", "identity": "remove", "path": CORE, "line": 14, "removed": True}
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

    assert _named(items) == NAMES_REMOVE
    assert _changed_code(items, COMPONENT, "Ledger.remove")["removed"] is True


def test_a_name_a_second_definition_made_ambiguous_is_not_called_removed(ledger: Path) -> None:
    """`parse_amount()` pairs with nothing once two functions have that name, and the one it
    named is still in its file, untouched, so the change removed nothing."""
    replace_text(ledger, CORE, *TOTAL_BODY)
    with (ledger / CLI).open("a", encoding="utf-8") as file:
        file.write(
            '\n\ndef parse_amount(text: str) -> int:\n    """Not the ledger\'s."""\n    return 0\n'
        )

    assert _named(_queue(ledger)) == NAMES_TOTAL


def test_a_method_added_under_a_functions_name_does_not_touch_the_function(ledger: Path) -> None:
    """`parse_amount()` pairs with nothing once a class of the same file has a method of that
    name. The function it named at the base is told from the method by its class, and no
    changed line is in it."""
    with (ledger / CORE).open("a", encoding="utf-8") as file:
        file.write(
            "\n\nclass Drawer:\n"
            '    """Coins, counted by hand."""\n\n'
            "    def parse_amount(self, text: str) -> int:\n"
            '        """Not the ledger\'s."""\n'
            "        return 0\n"
        )

    assert _queue(ledger) == []


def test_deleting_a_method_queues_the_sentence_that_names_it(ledger: Path) -> None:
    replace_text(ledger, CORE, REMOVE_METHOD, "")

    items = _queue(ledger)

    assert _named(items) == NAMES_REMOVE
    assert _changed_code(items, COMPONENT, "Ledger.remove")["removed"] is True


def test_a_command_whose_function_changed_queues_no_sentence_that_names_it(
    ledger: Path,
) -> None:
    """The requirement's fourth scenario: the usage guide and the README name `ledger list`,
    another guide names its `--limit`, and an option added to the command asks about none."""
    replace_text(
        ledger,
        CLI,
        '    limit: Annotated[int, typer.Option("--limit")] = 0,\n',
        '    limit: Annotated[int, typer.Option("--limit")] = 0,\n'
        '    as_json: Annotated[bool, typer.Option("--json")] = False,\n',
    )

    assert _queue(ledger) == []


def test_a_file_that_is_named_and_edited_queues_no_sentence_that_names_it(ledger: Path) -> None:
    """The requirement's fifth scenario: the README names `BACKLOG.md`."""
    with (ledger / "BACKLOG.md").open("a", encoding="utf-8") as file:
        file.write("\nPrint the ledger by month.\n")

    assert _queue(ledger) == []


@pytest.mark.parametrize(
    ("path", "old", "new"),
    [
        pytest.param(
            CLI, "def list_amounts(", "def list_all(", id="the-line-that-declares-a-command"
        ),
        pytest.param(CLI, "def report(", "def summary(", id="a-renamed-command"),
        pytest.param(CLI, '    """Print the total."""\n', "", id="a-line-deleted-from-a-command"),
        pytest.param(
            CLI,
            'typer.Option("--plain")',
            'typer.Option("--plain", help="The bare number.")',
            id="the-line-that-declares-an-option",
        ),
        pytest.param(
            DATES, '"%Y-%m-%d")', '"%d.%m.%Y")', id="the-line-that-reads-an-environment-variable"
        ),
        pytest.param(
            SERVER,
            "return Ledger().total()",
            "return Ledger().total() + 0",
            id="the-body-of-a-tool",
        ),
    ],
)
def test_nothing_but_a_function_or_class_is_paired_with_a_change(
    ledger: Path, path: str, old: str, new: str
) -> None:
    """The docs name the commands, both options, the environment variable and the tool whose
    code each of these edits. A renamed command is the one a finding answers for:
    `code-references/unknown-command` on each sentence that still names it."""
    replace_text(ledger, path, old, new)

    assert _queue(ledger) == []


def test_a_sentence_naming_a_source_file_is_not_queued_for_an_edit_to_it(ledger: Path) -> None:
    """The usage guide names `src/ledger/core.py`, and the component doc `parse_amount()`."""
    replace_text(ledger, CORE, "return round(float(text) * 100)", "return int(float(text) * 100)")

    items = _queue(ledger)

    assert _named(items) == {(COMPONENT, "parse_amount()")}
    assert _changed_code(items, COMPONENT, "parse_amount()")["line"] == 25


def test_renaming_a_file_queues_no_sentence_for_what_moved_with_it(ledger: Path) -> None:
    """A rename git follows keeps each definition where the working tree has it, so the
    sentences naming `Ledger` and its methods are not asked about: no line of them changed.
    The sentence that names the file by its old path is not paired either."""
    git(ledger, "mv", CORE, "src/ledger/book.py")

    assert _queue(ledger) == []


def test_deleting_a_file_queues_every_sentence_that_names_a_function_or_class_of_it(
    ledger: Path,
) -> None:
    (ledger / CORE).unlink()

    items = _queue(ledger)

    assert _named(items) == {
        NAMES_LEDGER,
        (COMPONENT, "Ledger.add"),
        (COMPONENT, "Ledger.remove"),
        (COMPONENT, "Ledger.total"),
        (COMPONENT, "parse_amount()"),
        (DECISION, "Ledger.add"),
    }
    assert all(code["removed"] for item in items for code in item["changed_code"])


def test_a_line_deleted_from_a_function_queues_the_sentences_that_name_it(ledger: Path) -> None:
    replace_text(ledger, CORE, '        """The sum of every amount."""\n', "")

    assert _named(_queue(ledger)) == NAMES_TOTAL


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
    replace_text(ledger, FEES, *FEE_BODY)

    assert _named(_queue(ledger)) == NAMES_FEE
    assert _named(_queue(ledger, "--base-ref", "origin/main")) == NAMES_ADD | NAMES_FEE
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

    assert _named(committed) == NAMES_TOTAL
    assert _changed_code(committed, COMPONENT, "Ledger.total")["line"] == 20


def test_a_committed_rename_is_read_from_the_merge_base(ledger: Path) -> None:
    git(ledger, "update-ref", "refs/remotes/origin/main", "HEAD")
    replace_text(ledger, CORE, "def remove(", "def delete(")
    commit_all(ledger, "remove is delete", when=LATER)

    for flags in (["--base-ref", "origin/main"], ["--base-ref", "origin/main", "--committed-only"]):
        items = _queue(ledger, *flags)
        assert _named(items) == NAMES_REMOVE, flags
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
        f"    changed: `Ledger.add` at {CORE}:12\n"
    ) in output
    assert (
        f"{COMPONENT}:18 ({MARKER})\n"
        "  `Ledger.remove` drops one amount and keeps the others in order.\n"
        f"    removed: `Ledger.remove`, at {CORE}:14 before this change\n"
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


def test_the_meaning_of_the_marker_is_true_of_the_json(ledger: Path) -> None:
    """One text defines the marker for both outputs, so it names nothing only the plain
    output prints: each name it writes as code is a key the JSON carries."""
    replace_text(ledger, CORE, *ADD_BODY)

    report = invoke_json(ledger, "list", "review", "--changed")

    [item] = [item for item in report["items"] if item["path"] == COMPONENT]
    keys = {*item, *item["changed_code"][0]}
    assert set(re.findall(r"`([^`]+)`", report["markers"][MARKER])) <= keys


def test_the_doc_filter_keeps_the_sentences_of_that_doc(ledger: Path) -> None:
    replace_text(ledger, CORE, *ADD_BODY)

    assert _named(_queue(ledger, "--doc", COMPONENT)) == {(COMPONENT, "Ledger.add")}


def test_the_help_of_changed_names_the_sentences_that_name_a_python_function_or_class() -> None:
    result = CliRunner().invoke(app, ["list", "review", "--help"], terminal_width=160)

    assert result.exit_code == 0, result.output
    # Rich may colour and wrap the help whatever width is asked for, as it does in CI.
    plain = re.sub(r"\x1b\[[0-9;]*m", "", result.output)
    text = " ".join(re.sub(r"[│╭╮╰╯─]", " ", plain).split())
    assert "the sentences in any doc that name a Python function or class it touched" in text


def test_the_edit_report_of_context_lists_none_of_these_sentences(ledger: Path) -> None:
    """The queue alone asks about them: the loop runs both commands, and the same sentences
    would be read twice."""
    replace_text(ledger, CORE, *ADD_BODY)

    code, output = invoke(ledger, "context", "--after-edit", "--format", "json")

    assert code == 0, output
    assert MARKER not in output
    assert "enters an amount" not in output
    assert "named_by" not in json.loads(output)
