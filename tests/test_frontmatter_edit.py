"""Tests for the shared frontmatter-edit helpers."""

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
    out = set_value("---\nstatus: draft\ntitle: Foo\nid: foo\n---\n\n# Foo\n", "status", "stable")
    # Keys are re-emitted in schema order: id, title, then status.
    assert out.index("id:") < out.index("title:") < out.index("status:")


def test_set_value_does_not_wrap_long_scalar_with_trailing_space() -> None:
    path = "docs/decisions/0009-implement-rfc-0018-decision-followups-and-maintenance-queue.md"
    out = set_value(DOC, "resolved_by", path)
    assert f"resolved_by: {path}\n" in out
    assert not any(line.endswith(" ") for line in out.splitlines())


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


def test_an_indented_delimiter_inside_a_block_scalar_is_not_the_end() -> None:
    doc = """\
---
id: foo
title: Foo
status: stable
summary: |
  A thing.
  ---
  Still the summary.
describes:
  - src/foo.py
---

# Foo

Body.
"""
    out = set_value(doc, "status", "deprecated")
    front, _, body = out.partition("\n---\n")

    assert "describes" in front, "a later key leaked out of the frontmatter"
    assert "Still the summary." in front
    assert body.strip() == "# Foo\n\nBody.".strip()


def test_reordering_keeps_the_comments_in_the_frontmatter() -> None:
    doc = """\
---
id: foo
# the reason this doc exists
title: Foo
status: stable
---

# Foo
"""
    assert "# the reason this doc exists" in set_value(doc, "status", "deprecated")
