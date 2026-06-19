"""The orient command vocabulary must stay accurate and complete vs the live CLI.

`irminsul orient` teaches a curated command vocabulary (`_COMMANDS` in
`irminsul.orient`). `test_packaged_vocabulary_matches_live_cli_surface` is the
drift gate: rename, remove, or add a command and it fails until `_COMMANDS` or
`_OMITTED` is updated. The `command_path`/`evaluate_vocabulary` unit tests pin the
evaluation logic itself.
"""

from __future__ import annotations

from pathlib import Path

from irminsul.config import find_config, load
from irminsul.inventory.cli_typer import CliTyperExtractor
from irminsul.orient import _COMMANDS, _OMITTED, command_path, evaluate_vocabulary


def test_command_path_strips_program_options_and_placeholders() -> None:
    assert command_path("irminsul context --changed") == "context"
    assert command_path("irminsul surface <kind> --format json") == "surface"
    assert command_path("irminsul list undocumented") == "list undocumented"
    assert command_path("irm refs <doc-or-symbol>") == "refs"


def test_evaluate_clean_vocabulary_has_no_issues() -> None:
    issues = evaluate_vocabulary(
        (("irminsul context --changed", "look before editing"),),
        ("init",),
        {"context", "init"},
    )
    assert issues == []


def test_evaluate_flags_removed_or_renamed_command() -> None:
    issues = evaluate_vocabulary((("irminsul frobnicate", "x"),), (), {"context"})
    assert any("frobnicate" in i and "not a current" in i for i in issues)


def test_evaluate_flags_missing_guidance() -> None:
    issues = evaluate_vocabulary((("irminsul context", ""),), (), {"context"})
    assert any("no guidance" in i for i in issues)


def test_evaluate_flags_rotted_omitted_entry() -> None:
    issues = evaluate_vocabulary((), ("gone",), {"context"})
    assert any("gone" in i and "omitted" in i for i in issues)


def test_evaluate_flags_new_uncovered_command() -> None:
    issues = evaluate_vocabulary((("irminsul context", "x"),), (), {"context", "brandnew"})
    assert any("brandnew" in i and "neither" in i for i in issues)


def test_evaluate_flags_new_uncovered_subcommand() -> None:
    # subcommand-precise: a new `list X` under an already-taught group is caught
    issues = evaluate_vocabulary(
        (("irminsul list undocumented", "x"),),
        (),
        {"list undocumented", "list duplicates"},
    )
    assert any("list duplicates" in i and "neither" in i for i in issues)


def test_packaged_vocabulary_matches_live_cli_surface() -> None:
    """The shipped vocabulary must stay consistent with irminsul's own CLI.

    Rename or remove an `irminsul` command, or add a new one, and this fails until
    `_COMMANDS`/`_OMITTED` in `irminsul.orient` is updated.
    """
    repo_root = Path(__file__).resolve().parent.parent
    pkg = repo_root / "src" / "irminsul"
    source_files = [(p, str(p.relative_to(repo_root))) for p in pkg.rglob("*.py")]
    config = load(find_config(repo_root))
    surface = {item.identity for item in CliTyperExtractor().extract(source_files, config)}

    issues = evaluate_vocabulary(_COMMANDS, _OMITTED, surface)
    assert issues == [], "\n".join(issues)
