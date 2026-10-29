"""A fact about a check lives on the check, so no list of check names can drift from the registry.

Four lists of check names used to sit beside the code that read them: the checks that
answer from commit history, the ones that take exceptions from the adoption record, the ones
registered but off by default, and the ones that reach the network. Rename a check or add a
sibling and the list was wrong without anything failing. Each is now a `CheckFlag` the check
declares, derived from the registry by `flagged`.
"""

from __future__ import annotations

import ast
from pathlib import Path

from irminsul.checks import REGISTRY, CheckFlag, flagged
from irminsul.checks.base import flags_of
from irminsul.checks.pipeline import PASSES, finding_sources

SRC = Path(__file__).resolve().parents[1] / "src" / "irminsul"

#: Spelled out here once so that a check losing its flag, or a flag changing meaning, fails a
#: test instead of quietly changing what a run does.
EXPECTED: dict[CheckFlag, set[str]] = {
    CheckFlag.opt_in: {"agents-manifest"},
    CheckFlag.reads_history: {
        "mtime-drift",
        "stale-reaper",
        "claim-provenance",
        "rfc-follow-through",
    },
    CheckFlag.consults_adoption_record: {"uniqueness", "test-ownership"},
    CheckFlag.uses_network: {"external-links"},
}


def hand_kept_lists(source: str, check_names: set[str]) -> list[str]:
    """The names bound to a literal list, tuple or set made only of registered check names."""
    out: list[str] = []
    for node in ast.walk(ast.parse(source)):
        if not isinstance(node, ast.Assign | ast.AnnAssign) or node.value is None:
            continue
        value = node.value
        if (
            isinstance(value, ast.Call)
            and isinstance(value.func, ast.Name)
            and value.func.id in {"frozenset", "set", "tuple", "list"}
            and len(value.args) == 1
        ):
            value = value.args[0]
        if not isinstance(value, ast.Set | ast.Tuple | ast.List) or not value.elts:
            continue
        strings = [
            element.value
            for element in value.elts
            if isinstance(element, ast.Constant) and isinstance(element.value, str)
        ]
        if len(strings) == len(value.elts) and set(strings) <= check_names:
            target = node.targets[0] if isinstance(node, ast.Assign) else node.target
            out.append(ast.unparse(target))
    return out


def test_each_flag_is_carried_by_exactly_the_checks_that_were_listed() -> None:
    assert {flag: set(flagged(flag)) for flag in CheckFlag} == EXPECTED


def test_a_new_flag_has_to_be_pinned_here() -> None:
    assert set(EXPECTED) == set(CheckFlag)


def test_only_registered_checks_declare_flags() -> None:
    """`flagged` reads the registry, so a flag on a pass would be ignored without a word."""
    declared_elsewhere = {
        name: sorted(flags_of(cls))
        for name, cls in finding_sources().items()
        if name not in REGISTRY and flags_of(cls)
    }
    assert declared_elsewhere == {}
    assert PASSES, "no passes registered, so the line above proves nothing"


def test_no_module_keeps_a_list_of_check_names() -> None:
    names = set(finding_sources())
    found = {
        f"{path.relative_to(SRC).as_posix()}:{name}"
        for path in sorted(SRC.rglob("*.py"))
        for name in hand_kept_lists(path.read_text(encoding="utf-8"), names)
    }
    assert found == set()


def test_the_scan_finds_a_planted_list() -> None:
    planted = (
        'OPT_IN = ("agents-manifest",)\n'
        'MIXED = frozenset({"links", "not-a-check"})\n'
        'class C:\n    HISTORY: Final = frozenset({"mtime-drift", "stale-reaper"})\n'
        'EMPTY = ()\nOTHER = ["links", 3]\n'
    )
    assert hand_kept_lists(planted, set(REGISTRY)) == ["OPT_IN", "HISTORY"]
