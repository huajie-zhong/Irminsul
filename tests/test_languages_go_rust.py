"""Tests for Go and Rust language profiles."""

from __future__ import annotations

from irminsul.languages import LANGUAGE_REGISTRY


def test_registry_contains_go() -> None:
    assert "go" in LANGUAGE_REGISTRY
    assert LANGUAGE_REGISTRY["go"].name == "go"


def test_registry_contains_rust() -> None:
    assert "rust" in LANGUAGE_REGISTRY


def test_go_struct_pattern_matches() -> None:
    profile = LANGUAGE_REGISTRY["go"]
    assert any(p.search("type User struct {") for p in profile.schema_leak_patterns)
    assert any(p.search("    type User struct {") for p in profile.schema_leak_patterns)


def test_go_interface_pattern_matches() -> None:
    profile = LANGUAGE_REGISTRY["go"]
    assert any(p.search("type Reader interface {") for p in profile.schema_leak_patterns)


def test_go_method_pattern_matches() -> None:
    profile = LANGUAGE_REGISTRY["go"]
    assert any(p.search("func (u *User) Greet() string {") for p in profile.schema_leak_patterns)


def test_go_negative_does_not_match_prose() -> None:
    profile = LANGUAGE_REGISTRY["go"]
    line = "The User struct lives in the package."
    assert not any(p.search(line) for p in profile.schema_leak_patterns)


def test_rust_struct_pattern_matches() -> None:
    profile = LANGUAGE_REGISTRY["rust"]
    assert any(p.search("pub struct User {") for p in profile.schema_leak_patterns)
    assert any(p.search("struct User<T> {") for p in profile.schema_leak_patterns)


def test_rust_enum_pattern_matches() -> None:
    profile = LANGUAGE_REGISTRY["rust"]
    assert any(p.search("pub enum Color {") for p in profile.schema_leak_patterns)


def test_rust_trait_pattern_matches() -> None:
    profile = LANGUAGE_REGISTRY["rust"]
    assert any(p.search("pub trait Reader {") for p in profile.schema_leak_patterns)
    assert any(p.search("trait Display: Debug {") for p in profile.schema_leak_patterns)


def test_rust_impl_pattern_matches() -> None:
    profile = LANGUAGE_REGISTRY["rust"]
    assert any(p.search("impl User {") for p in profile.schema_leak_patterns)
    assert any(p.search("impl<T> Display for Box<T> {") for p in profile.schema_leak_patterns)


def test_rust_negative_does_not_match_prose() -> None:
    profile = LANGUAGE_REGISTRY["rust"]
    assert not any(
        p.search("the trait system in Rust is rich") for p in profile.schema_leak_patterns
    )
