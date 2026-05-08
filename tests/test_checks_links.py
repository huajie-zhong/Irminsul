"""Tests for the LinksCheck."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from irminsul.checks import Severity
from irminsul.checks.links import LinksCheck
from irminsul.config import load
from irminsul.docgraph import build_graph


def _run(repo: Path) -> list:
    cfg = load(repo / "irminsul.toml")
    graph = build_graph(repo, cfg)
    return LinksCheck().run(graph)


def test_good_fixture_has_no_link_findings(
    fixture_repo: Callable[[str], Path],
) -> None:
    findings = _run(fixture_repo("good"))
    assert findings == []


def test_bad_links_flags_broken_relative_targets(
    fixture_repo: Callable[[str], Path],
) -> None:
    findings = _run(fixture_repo("bad-links"))
    error_messages = [f.message for f in findings if f.severity == Severity.error]

    assert any("does-not-exist.md" in m for m in error_messages)
    assert any("nope.md" in m for m in error_messages)


def test_bad_links_skips_external_and_anchor_only(
    fixture_repo: Callable[[str], Path],
) -> None:
    findings = _run(fixture_repo("bad-links"))
    error_messages = [f.message for f in findings if f.severity == Severity.error]

    # External URLs and mailto: must NOT be flagged.
    assert not any("https://example.com" in m for m in error_messages)
    assert not any("mailto:" in m for m in error_messages)
    # Anchor-only links (no target file) must NOT be flagged.
    assert not any(m.endswith("'#linker'") for m in error_messages)


def test_bad_links_resolves_through_anchors(
    fixture_repo: Callable[[str], Path],
) -> None:
    """A link like `[x](neighbor.md#heading)` should resolve to neighbor.md
    (which exists) — i.e. NOT flagged."""
    findings = _run(fixture_repo("bad-links"))
    error_messages = [f.message for f in findings if f.severity == Severity.error]
    # neighbor.md exists, so the anchor variant must not be a broken link.
    # We only check that the existing file's anchored form isn't flagged.
    assert not any("neighbor.md#heading" in m for m in error_messages)
