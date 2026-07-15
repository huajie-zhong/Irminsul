"""Tests for implemented-RFC content seals."""

from __future__ import annotations

from irminsul.rfc_freeze import compute_frozen_hash, seal_text

_RFC = """---
id: 0001-example
title: Example
audience: explanation
tier: 2
status: stable
rfc_state: implemented
resolved_by: docs/50-decisions/0001-example.md
---

# RFC 0001

Historical proposal.
"""


def test_seal_text_writes_a_verifiable_full_sha256() -> None:
    sealed = seal_text(_RFC)
    [line] = [line for line in sealed.splitlines() if line.startswith("frozen_hash:")]
    stored = line.removeprefix('frozen_hash: "').removesuffix('"')
    assert stored.startswith("sha256:")
    assert len(stored) == 71
    assert compute_frozen_hash(sealed) == stored


def test_seal_text_is_idempotent() -> None:
    sealed = seal_text(_RFC)
    assert seal_text(sealed) == sealed


def test_hash_detects_body_and_frontmatter_edits() -> None:
    sealed = seal_text(_RFC)
    original = compute_frozen_hash(sealed)
    assert compute_frozen_hash(sealed.replace("Historical", "Extended")) != original
    assert compute_frozen_hash(sealed.replace("title: Example", "title: Revised")) != original


def test_hash_normalizes_line_endings() -> None:
    sealed = seal_text(_RFC)
    assert compute_frozen_hash(sealed) == compute_frozen_hash(sealed.replace("\n", "\r\n"))
