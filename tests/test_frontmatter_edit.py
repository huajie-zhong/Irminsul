"""Tests for the shared frontmatter-edit helpers (RFC 0022)."""

from __future__ import annotations

from irminsul.frontmatter_edit import (
    add_to_list,
    remove_inventory_item,
    set_value,
)

DOC = """\
---
id: foo
title: Foo
status: draft
---

# Foo

Body stays untouched.
"""


def test_set_value_changes_scalar_and_keeps_body() -> None:
    out = set_value(DOC, "status", "stable")
    assert "status: stable" in out
    assert "Body stays untouched." in out
    assert "# Foo" in out


def test_set_value_is_idempotent_noop() -> None:
    assert set_value(DOC, "status", "draft") == DOC


def test_set_value_canonical_order() -> None:
    out = set_value(DOC, "audience", "explanation")
    # `audience` is a canonical field that sorts before `status`.
    assert out.index("audience:") < out.index("status:")


def test_add_to_list_creates_and_appends() -> None:
    once = add_to_list(DOC, "implements", "0018-x")
    assert "implements:" in once
    assert "0018-x" in once
    twice = add_to_list(once, "implements", "0099-y")
    assert "0018-x" in twice and "0099-y" in twice


def test_add_to_list_is_idempotent_on_existing_value() -> None:
    once = add_to_list(DOC, "implements", "0018-x")
    assert add_to_list(once, "implements", "0018-x") == once


def test_remove_inventory_item_drops_only_named_item() -> None:
    doc = """\
---
id: foo
title: Foo
status: draft
inventory:
  - kind: cli
    items: [alpha, beta]
---

Body.
"""
    out = remove_inventory_item(doc, "cli", "beta")
    assert "alpha" in out
    assert "beta" not in out
    assert "kind: cli" in out  # entry preserved even after removal


def test_remove_inventory_item_noop_when_absent() -> None:
    doc = """\
---
id: foo
title: Foo
status: draft
inventory:
  - kind: cli
    items: [alpha]
---

Body.
"""
    assert remove_inventory_item(doc, "cli", "missing") == doc
    assert remove_inventory_item(doc, "http", "alpha") == doc
