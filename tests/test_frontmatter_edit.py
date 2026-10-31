"""Tests for the shared frontmatter-edit helpers."""

from __future__ import annotations

import pytest

from irminsul.frontmatter_edit import (
    add_to_list,
    remove_inventory_item,
    set_value,
    strip_claim_pins,
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

PINNED = """\
---
id: foo
title: Foo
status: stable
claims:
  - id: first
    state: implemented
    kind: invariant
    claim: The first holds.
    evidence:
      - src/a.py
    pinned:
      src/a.py: sha256:aaaa
  - id: second
    state: implemented
    kind: invariant
    claim: The second holds.
    evidence:
      - src/b.py
    pinned:
      src/b.py: sha256:bbbb
---

# Foo

Body stays untouched.
"""

PINNED_FIRST = """\
---
id: foo
title: Foo
status: stable
claims:
  - pinned:
      src/a.py: sha256:aaaa
    id: first
    state: implemented
    kind: invariant
    claim: The first holds.
    evidence:
      - src/a.py
---

Body.
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


INDENTED = """\
---
id: foo
title: Foo
status: stable
describes:
  - src/a.py
claims:
  - id: c
    state: implemented
    kind: invariant
    claim: A sentence long enough to pass the eighty columns ruamel would otherwise wrap at.
    evidence:
      - src/a.py
---

# Foo
"""


def test_an_edit_keeps_the_lists_indented_as_the_doc_wrote_them() -> None:
    out = set_value(INDENTED, "status", "deprecated")
    assert out == INDENTED.replace("status: stable", "status: deprecated")


def test_a_doc_with_flush_lists_keeps_them_flush() -> None:
    flush = "---\nid: foo\ntitle: Foo\nstatus: stable\ndescribes:\n- src/a.py\n---\n\n# Foo\n"
    out = add_to_list(flush, "describes", "src/b.py")
    assert out == flush.replace("- src/a.py\n", "- src/a.py\n- src/b.py\n")


def test_strip_claim_pins_removes_each_claims_pinned_map_and_keeps_the_rest() -> None:
    stripped = strip_claim_pins(PINNED)

    assert "pinned" not in stripped
    assert "src/a.py: sha256:aaaa" not in stripped
    assert "claim: The second holds." in stripped
    assert stripped.endswith("---\n\n# Foo\n\nBody stays untouched.\n")


def test_strip_claim_pins_removes_a_pinned_key_that_opens_a_claim() -> None:
    assert "pinned" not in strip_claim_pins(PINNED_FIRST)
    assert "id: first" in strip_claim_pins(PINNED_FIRST)


def test_a_re_pin_leaves_the_stripped_frontmatter_unchanged() -> None:
    repinned = PINNED_FIRST.replace("sha256:aaaa", "sha256:cccc")

    assert strip_claim_pins(repinned) == strip_claim_pins(PINNED_FIRST)


def test_a_pinned_line_inside_a_block_scalar_is_prose_not_a_pin() -> None:
    doc = PINNED.replace(
        "claim: The first holds.",
        "claim: |\n      The first holds.\n      pinned: this line is prose",
    )

    stripped = strip_claim_pins(doc)

    assert "pinned: this line is prose" in stripped
    assert "src/a.py: sha256:aaaa" not in stripped


@pytest.mark.parametrize(
    "text",
    [
        "",
        "Just a fragment, `pinned: yes`.\n",
        "---\nid: foo\nclaims: [unclosed\n---\nBody.\n",
        "---\n- not\n- a mapping\n---\nBody.\n",
        "---\nid: foo\nclaims:\n  - id: a\n  - [\n---\nBody.\n",
    ],
)
def test_strip_claim_pins_returns_text_it_cannot_read_unchanged(text: str) -> None:
    assert strip_claim_pins(text) == text
