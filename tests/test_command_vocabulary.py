"""Tests for the agent command vocabulary: parser, drift evaluation, and the
real packaged data staying consistent with the live CLI surface."""

from __future__ import annotations

from pathlib import Path

from irminsul.command_vocabulary import (
    CommandHint,
    Vocabulary,
    command_path,
    evaluate_vocabulary,
    load_vocabulary,
    parse_vocabulary,
)
from irminsul.config import find_config, load
from irminsul.inventory.cli_typer import CliTyperExtractor

_SAMPLE = """\
# Vocabulary

## Commands

| command | when |
| --- | --- |
| `irminsul context --changed` | look before editing |
| `irminsul list undocumented` | find uncovered files |

## Omitted

- `init`
- `seed`
"""


def test_parse_vocabulary_reads_table_and_omitted() -> None:
    vocab = parse_vocabulary(_SAMPLE)
    assert vocab.commands == [
        CommandHint(command="irminsul context --changed", when="look before editing"),
        CommandHint(command="irminsul list undocumented", when="find uncovered files"),
    ]
    assert vocab.omitted == ["init", "seed"]


def test_command_path_strips_program_options_and_placeholders() -> None:
    assert command_path("irminsul context --changed") == "context"
    assert command_path("irminsul surface <kind> --format json") == "surface"
    assert command_path("irminsul list undocumented") == "list undocumented"
    assert command_path("irm refs <doc-or-symbol>") == "refs"


def test_evaluate_clean_vocabulary_has_no_issues() -> None:
    vocab = Vocabulary(
        commands=[CommandHint(command="irminsul context --changed", when="x")],
        omitted=["init"],
    )
    assert evaluate_vocabulary(vocab, {"context", "init"}) == []


def test_evaluate_flags_removed_or_renamed_command() -> None:
    vocab = Vocabulary(
        commands=[CommandHint(command="irminsul frobnicate", when="x")],
        omitted=[],
    )
    issues = evaluate_vocabulary(vocab, {"context"})
    assert any(
        "frobnicate" in issue.message and "not a current" in issue.message for issue in issues
    )


def test_evaluate_flags_missing_when_guidance() -> None:
    vocab = Vocabulary(commands=[CommandHint(command="irminsul context", when="")], omitted=[])
    issues = evaluate_vocabulary(vocab, {"context"})
    assert any("no 'when' guidance" in issue.message for issue in issues)


def test_evaluate_flags_rotted_omitted_entry() -> None:
    vocab = Vocabulary(commands=[], omitted=["gone"])
    issues = evaluate_vocabulary(vocab, {"context"})
    assert any("'gone'" in issue.message and "omitted" in issue.message for issue in issues)


def test_evaluate_flags_new_uncovered_command() -> None:
    vocab = Vocabulary(
        commands=[CommandHint(command="irminsul context", when="x")],
        omitted=[],
    )
    issues = evaluate_vocabulary(vocab, {"context", "brandnew"})
    assert any("'brandnew'" in issue.message and "neither" in issue.message for issue in issues)


def test_packaged_vocabulary_matches_live_cli_surface() -> None:
    """The shipped vocabulary must stay consistent with irminsul's own CLI.

    This is the drift gate: rename or remove an `irminsul` command, or add a new
    top-level one, and this test fails until the data file is updated.
    """
    repo_root = Path(__file__).resolve().parent.parent
    pkg = repo_root / "src" / "irminsul"
    source_files = [(p, str(p.relative_to(repo_root))) for p in pkg.rglob("*.py")]
    config = load(find_config(repo_root))
    surface = {item.identity for item in CliTyperExtractor().extract(source_files, config)}

    vocab = load_vocabulary()
    issues = evaluate_vocabulary(vocab, surface)
    assert issues == [], "\n".join(issue.message for issue in issues)
