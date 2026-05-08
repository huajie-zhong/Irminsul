"""Smoke tests for language profile registry and pattern compilation."""

from __future__ import annotations

from irminsul.languages import LANGUAGE_REGISTRY, PYTHON_PROFILE, TYPESCRIPT_PROFILE


def test_registry_has_python_and_typescript() -> None:
    assert "python" in LANGUAGE_REGISTRY
    assert "typescript" in LANGUAGE_REGISTRY
    assert LANGUAGE_REGISTRY["python"] is PYTHON_PROFILE
    assert LANGUAGE_REGISTRY["typescript"] is TYPESCRIPT_PROFILE


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
