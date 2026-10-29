"""One reading of a declared test path, across the consumers that used to disagree.

`tests: [tests/]` used to mean three different things at once: `coverage` saw a directory
that exists and passed it, `change/footprint` matched every file under it, and `context`
compared raw strings and matched nothing. These pin the single answer.
"""

from __future__ import annotations

from pathlib import Path

from irminsul.config import IrminsulConfig, Languages, Paths
from irminsul.declared_tests import (
    classify_test_reference,
    configured_test_patterns,
    is_test_path,
    matching_paths,
)

_CANDIDATES = [
    "tests/test_cli.py",
    "tests/sub/test_deep.py",
    "tests/helpers.py",
    "src/core.py",
]


def test_a_trailing_slash_is_a_directory() -> None:
    assert classify_test_reference("tests/").kind == "directory"


def test_a_wildcard_is_a_pattern() -> None:
    assert classify_test_reference("tests/test_*.py").kind == "pattern"


def test_a_plain_path_is_a_file_whether_or_not_it_exists() -> None:
    assert classify_test_reference("tests/test_cli.py").kind == "file"
    assert classify_test_reference("tests/gone.py").is_exact


def test_a_real_directory_is_one_without_the_slash(tmp_path: Path) -> None:
    (tmp_path / "tests").mkdir()

    assert classify_test_reference("tests", tmp_path).kind == "directory"


def test_a_directory_reaches_everything_under_it() -> None:
    assert matching_paths(["tests/"], _CANDIDATES) == [
        "tests/helpers.py",
        "tests/sub/test_deep.py",
        "tests/test_cli.py",
    ]


def test_a_directory_written_without_a_slash_matches_the_same() -> None:
    assert matching_paths(["tests"], _CANDIDATES) == matching_paths(["tests/"], _CANDIDATES)


def test_a_glob_matches_only_its_own_level() -> None:
    assert matching_paths(["tests/test_*.py"], _CANDIDATES) == ["tests/test_cli.py"]


def test_an_exact_entry_matches_itself() -> None:
    assert matching_paths(["tests/test_cli.py"], _CANDIDATES) == ["tests/test_cli.py"]


def test_no_entries_match_nothing() -> None:
    assert matching_paths([], _CANDIDATES) == []


def _config(*, languages: list[str], test_patterns: list[str] | None = None) -> IrminsulConfig:
    return IrminsulConfig(
        paths=Paths(docs_root="docs", source_roots=["src"], test_patterns=test_patterns or []),
        languages=Languages(enabled=languages),
    )


def test_go_recognises_a_colocated_test() -> None:
    config = _config(languages=["go"])

    assert is_test_path("parser/parser_test.go", config)
    assert not is_test_path("parser/parser.go", config)


def test_python_and_typescript_conventions() -> None:
    config = _config(languages=["python", "typescript"])

    assert is_test_path("tests/test_cli.py", config)
    assert is_test_path("src/thing.spec.ts", config)
    assert not is_test_path("src/thing.ts", config)


def test_a_project_can_replace_the_conventions() -> None:
    config = _config(languages=["python"], test_patterns=["spec/**"])

    assert is_test_path("spec/anything.py", config)
    assert not is_test_path("tests/test_cli.py", config)
    assert configured_test_patterns(config) == ("spec/**",)


def test_a_language_with_no_filename_convention_recognises_nothing() -> None:
    """Rust keeps unit tests inside the module they cover, so no pattern can see them and
    the ownership rule simply does not reach that repository until it says otherwise."""
    config = _config(languages=["rust"])

    assert configured_test_patterns(config) == ()
    assert not is_test_path("src/lib.rs", config)
