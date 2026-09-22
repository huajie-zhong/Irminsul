"""Tests for RfcFollowThroughCheck.fixes."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from irminsul.checks.rfc_follow_through import RfcFollowThroughCheck
from irminsul.config import find_config, load
from irminsul.docgraph import build_graph
from irminsul.fix import apply_fixes


def _fixes(repo: Path) -> list:
    config = load(find_config(repo))
    graph = build_graph(repo, config)
    check = RfcFollowThroughCheck()
    return check.fixes(check.run(graph), graph)


def test_metadata_fixes_require_confirm(fixture_repo: Callable[[str], Path]) -> None:
    repo = fixture_repo("soft-rfc-follow-through")
    fixes = _fixes(repo)
    assert fixes  # there is drift to fix
    assert all(f.requires_confirm for f in fixes)

    rfc = repo / "docs" / "rfcs" / "0002-accepted-bad-status.md"
    before = rfc.read_text(encoding="utf-8")
    apply_fixes(repo, fixes, dry_run=False, confirm=False)
    assert rfc.read_text(encoding="utf-8") == before  # held


def test_accepted_status_bumped_on_confirm(fixture_repo: Callable[[str], Path]) -> None:
    repo = fixture_repo("soft-rfc-follow-through")
    apply_fixes(repo, _fixes(repo), dry_run=False, confirm=True)

    rfc = repo / "docs" / "rfcs" / "0002-accepted-bad-status.md"
    text = rfc.read_text(encoding="utf-8")
    assert "status: stable" in text


def test_fixes_are_idempotent(fixture_repo: Callable[[str], Path]) -> None:
    repo = fixture_repo("soft-rfc-follow-through")
    apply_fixes(repo, _fixes(repo), dry_run=False, confirm=True)
    # Re-running on the fixed tree converges: nothing left for the bumped docs.
    second = _fixes(repo)
    paths = {f.path.as_posix() for f in second}
    assert "docs/rfcs/0002-accepted-bad-status.md" not in paths
    assert "docs/rfcs/0005-withdrawn-bad.md" not in paths


def test_appending_a_section_twice_leaves_one(tmp_path: Path) -> None:
    """The stub used to be appended on every run when the heading did not render."""
    from irminsul.checks.rfc_follow_through import append_section

    once = append_section("# RFC\n\nBody.\n", "Resolution")
    assert append_section(once, "Resolution") == once

    # A heading swallowed by an unclosed fence renders as code, not as a heading.
    fenced = "# RFC\n\n```\n## Resolution\n"
    assert append_section(fenced, "Resolution") == fenced
