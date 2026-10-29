"""Tests for `OrphansCheck`."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from irminsul.checks.orphans import OrphansCheck

from .conftest import run_check, write_config, write_doc


def test_orphan_doc_flagged(fixture_repo: Callable[[str], Path]) -> None:
    repo = fixture_repo("soft-orphans")

    findings = run_check(OrphansCheck, repo)
    flagged_ids = {f.doc_id for f in findings}
    assert "stranded" in flagged_ids


def test_index_doc_exempt(fixture_repo: Callable[[str], Path]) -> None:
    repo = fixture_repo("soft-orphans")

    findings = run_check(OrphansCheck, repo)
    flagged_ids = {f.doc_id for f in findings}
    assert "widget" not in flagged_ids


def test_layer_doc_with_back_link_not_orphan(fixture_repo: Callable[[str], Path]) -> None:
    """A layer-entry doc is only safe from the orphan check when something
    actually links to it. The fixture has `hub.md` link back to `overview.md`."""
    repo = fixture_repo("soft-orphans")

    findings = run_check(OrphansCheck, repo)
    flagged_ids = {f.doc_id for f in findings}
    assert "overview" not in flagged_ids


def test_adr_exempt(fixture_repo: Callable[[str], Path]) -> None:
    repo = fixture_repo("soft-orphans")

    findings = run_check(OrphansCheck, repo)
    flagged_ids = {f.doc_id for f in findings}
    assert "0001-pick-something" not in flagged_ids


def test_doc_with_inbound_link_not_orphan(fixture_repo: Callable[[str], Path]) -> None:
    repo = fixture_repo("soft-orphans")

    findings = run_check(OrphansCheck, repo)
    flagged_ids = {f.doc_id for f in findings}
    assert "hub" not in flagged_ids


def test_sibling_of_index_not_orphan(fixture_repo: Callable[[str], Path]) -> None:
    repo = fixture_repo("soft-orphans")

    findings = run_check(OrphansCheck, repo)
    flagged_ids = {f.doc_id for f in findings}
    assert "widget-internals" not in flagged_ids


def test_finding_has_suggestion(fixture_repo: Callable[[str], Path]) -> None:
    repo = fixture_repo("soft-orphans")

    findings = run_check(OrphansCheck, repo)
    stranded = next(f for f in findings if f.doc_id == "stranded")
    assert stranded.suggestion is not None
    assert "INDEX" in stranded.suggestion or "link" in stranded.suggestion.lower()


def test_an_rfc_whose_resolved_by_names_a_doc_is_not_an_orphan(tmp_path: Path) -> None:
    """Nothing links to the RFC and the record does not link back: only its own
    `resolved_by` places it, and only when it names a doc that exists."""
    write_config(tmp_path)
    write_doc(tmp_path, "docs/decisions/record.md", doc_id="record", body="Decides.")
    write_doc(
        tmp_path,
        "docs/rfcs/resolved.md",
        doc_id="resolved",
        body="Proposes.",
        frontmatter_extra=["rfc_state: implemented", "resolved_by: docs/decisions/record.md"],
    )
    write_doc(
        tmp_path,
        "docs/rfcs/dangling.md",
        doc_id="dangling",
        body="Proposes.",
        frontmatter_extra=["rfc_state: implemented", "resolved_by: docs/decisions/gone.md"],
    )
    write_doc(tmp_path, "docs/rfcs/open.md", doc_id="open", body="Proposes.")

    flagged = {f.doc_id for f in run_check(OrphansCheck, tmp_path)}

    assert flagged == {"dangling", "open"}
