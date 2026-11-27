"""Smoke tests for language profile registry and pattern compilation."""

from __future__ import annotations

import ast
import re
from pathlib import Path

import pytest

import irminsul.checks
from irminsul.checks.file_paths import FileIndex
from irminsul.checks.globs import walk_configured_source_files
from irminsul.checks.inventory_drift import _invoked_program
from irminsul.checks.uniqueness import omitted_from_source_ownership
from irminsul.languages import (
    LANGUAGE_REGISTRY,
    PYTHON_PROFILE,
    TYPESCRIPT_PROFILE,
    LanguageProfile,
)

from .conftest import load_graph, write, write_config


def test_registry_has_python_and_typescript() -> None:
    assert "python" in LANGUAGE_REGISTRY
    assert "typescript" in LANGUAGE_REGISTRY
    assert LANGUAGE_REGISTRY["python"] is PYTHON_PROFILE
    assert LANGUAGE_REGISTRY["typescript"] is TYPESCRIPT_PROFILE


@pytest.mark.parametrize("name", list(LANGUAGE_REGISTRY))
def test_a_profile_lists_the_files_that_mark_its_language(name: str) -> None:
    """Detection, the code-or-no-code test and every extractor's file selection read these."""
    profile = LANGUAGE_REGISTRY[name]
    assert profile.suffixes
    assert all(suffix.startswith(".") for suffix in profile.suffixes)
    assert profile.markers


def test_no_two_profiles_claim_one_suffix() -> None:
    suffixes = [suffix for profile in LANGUAGE_REGISTRY.values() for suffix in profile.suffixes]
    assert len(suffixes) == len(set(suffixes))


def test_python_patterns_match_expected_lines() -> None:
    patterns = PYTHON_PROFILE.schema_leak_patterns
    matches = lambda line: any(p.search(line) for p in patterns)  # noqa: E731

    assert matches("class Thing(BaseModel):")
    assert matches("    class Nested(BaseModel):")
    assert matches("class Order(SomethingBase, Mixin):")
    assert matches("class Service(Protocol):")
    assert matches("@dataclass")
    assert matches("@dataclass(frozen=True)")
    assert matches("CREATE TABLE foo (id INT);")
    assert matches("create view bar as select 1;")

    # Prose mentions and unrelated code shouldn't match.
    assert not matches("The class lives in app/thing.py.")
    assert not matches("def regular_function():")
    assert not matches("# class Thing(BaseModel) is just a comment example, no it isn't")


def test_typescript_patterns_match_expected_lines() -> None:
    patterns = TYPESCRIPT_PROFILE.schema_leak_patterns
    matches = lambda line: any(p.search(line) for p in patterns)  # noqa: E731

    assert matches("interface Thing {")
    assert matches("export interface Thing {")
    assert matches("interface Thing extends Other {")
    assert matches("type Thing =")
    assert matches("export type Thing = string;")
    assert matches("enum Color {")

    assert not matches("This interface is documented elsewhere.")
    assert not matches("const x = 1;")


def _seen_by_the_checks(repo: Path) -> tuple[object, ...]:
    graph = load_graph(repo)
    index = FileIndex(graph)
    return (
        sorted(display for _, display in walk_configured_source_files(repo, graph.config).files),
        omitted_from_source_ownership("src/desk/mod.gox", None),
        index.holds("gox_cache/desk.gox", ""),
        index.holds("other/NOTICE.txt", ""),
        index.holds("lib/ACTIVATE.txt", ""),
        _invoked_program(["goxpm", "run", "irminsul", "check"]),
        _invoked_program(["gox1.2", "-q", "-m", "irminsul", "check"]),
    )


def test_a_registered_language_is_known_to_each_check_by_its_profile(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A made-up language's files and tools are its profile's lists. Once it is registered
    the source walk leaves out what its tools wrote, `uniqueness` asks no doc for its
    `mod.gox`, the file index leaves out what it installed, and `inventory-drift` looks past
    its package manager and its interpreter, with no check edited."""
    for rel in (
        "src/desk/desk.gox",
        "src/desk/mod.gox",
        "src/desk/desk.goxc",
        "src/desk/gox_cache/desk.gox",
        "gox_modules/other/NOTICE.txt",
        "env/gox.cfg",
        "env/lib/ACTIVATE.txt",
    ):
        write(tmp_path, rel, "")
    write_config(tmp_path, source_roots=["src"])
    every_file = [
        "src/desk/desk.gox",
        "src/desk/desk.goxc",
        "src/desk/gox_cache/desk.gox",
        "src/desk/mod.gox",
    ]

    assert _seen_by_the_checks(tmp_path) == (
        every_file,
        False,
        True,
        True,
        True,
        "goxpm",
        "gox1.2",
    )

    monkeypatch.setitem(
        LANGUAGE_REGISTRY,
        "gox",
        LanguageProfile(
            name="gox",
            source_root_candidates=(),
            schema_leak_patterns=(),
            suffixes=(".gox",),
            unclaimed_files=("mod.gox",),
            cache_dirs=("gox_cache",),
            compiled_suffixes=(".goxc",),
            dependency_dirs=("gox_modules",),
            environment_markers=("gox.cfg",),
            launchers=("goxpm",),
            interpreter=re.compile(r"gox[\d.]*"),
        ),
    )

    assert _seen_by_the_checks(tmp_path) == (
        ["src/desk/desk.gox", "src/desk/mod.gox"],
        True,
        False,
        False,
        False,
        "irminsul",
        "irminsul",
    )


def test_no_check_holds_a_name_a_profile_lists() -> None:
    """A check that kept one of a language's files or tools in a string of its own would
    have to be edited to add a language, so what a profile lists, and a profile's name, no
    check's code repeats. A docstring may name one as an example."""
    listed = {
        value
        for profile in LANGUAGE_REGISTRY.values()
        for values in (
            (profile.name,),
            profile.suffixes,
            profile.unclaimed_files,
            profile.cache_dirs,
            profile.compiled_suffixes,
            profile.dependency_dirs,
            profile.environment_markers,
            profile.launchers,
        )
        for value in values
    }
    repeated: dict[str, list[str]] = {}
    [checks_dir] = irminsul.checks.__path__
    for path in sorted(Path(checks_dir).glob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        docstrings = {
            id(node.value)
            for node in ast.walk(tree)
            if isinstance(node, ast.Expr) and isinstance(node.value, ast.Constant)
        }
        found = sorted(
            {
                node.value
                for node in ast.walk(tree)
                if isinstance(node, ast.Constant)
                and isinstance(node.value, str)
                and id(node) not in docstrings
                and node.value in listed
            }
        )
        if found:
            repeated[path.name] = found

    assert len(listed) > 20
    assert repeated == {}
