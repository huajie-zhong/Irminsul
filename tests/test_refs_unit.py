"""Unit tests for the report builders in `irminsul.refs`.

These exercise the pure report-building functions directly against fixture
repos (no CLI), pinning backlink resolution, fnmatch symbol matching, and the
JSON shapes downstream tooling parses.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from pathlib import Path

import pytest

from irminsul.config import find_config, load
from irminsul.docgraph import DocGraph, build_graph
from irminsul.refs import (
    RefsError,
    build_doc_refs_report,
    build_symbol_refs_report,
    doc_refs_report_to_json,
    symbol_refs_report_to_json,
)

FixtureRepo = Callable[[str], Path]


def _graph(repo: Path) -> DocGraph:
    return build_graph(repo, load(find_config(repo)))


def test_strong_backlinks_come_from_depends_on(fixture_repo: FixtureRepo) -> None:
    repo = fixture_repo("soft-lifecycle")
    report = build_doc_refs_report(repo, _graph(repo), "0007-depends-on-only")

    assert report.target == "0007-depends-on-only"
    # Strong inbound refs come from `depends_on` plus the resolving ADR
    # (`resolved_by` is recorded as an inbound strong edge to the RFC).
    assert [hit.doc_id for hit in report.strong] == ["0001-good-adr", "depends-on-only"]
    depends_hit = report.strong[1]
    assert depends_hit.path == "docs/20-components/depends-on-only.md"
    # Line points at the `- 0007-depends-on-only` entry inside the
    # `depends_on:` frontmatter list, not at the top of the file.
    assert depends_hit.line == 9
    # The resolved_by edge has no `depends_on` entry to point at: line falls
    # back to 1.
    assert report.strong[0].line == 1
    assert report.weak == []


def test_weak_backlinks_resolve_relative_markdown_links(fixture_repo: FixtureRepo) -> None:
    repo = fixture_repo("soft-orphans")
    report = build_doc_refs_report(repo, _graph(repo), "hub")

    assert report.strong == []
    assert [hit.doc_id for hit in report.weak] == ["overview"]
    hit = report.weak[0]
    assert hit.path == "docs/10-architecture/overview.md"
    # The link lives in the final paragraph of overview.md; the reported line
    # is file-absolute (frontmatter offset included), not body-relative.
    assert hit.line == 14


def test_target_resolves_by_repo_relative_path(fixture_repo: FixtureRepo) -> None:
    repo = fixture_repo("soft-orphans")
    report = build_doc_refs_report(repo, _graph(repo), "docs/20-components/hub.md")
    assert report.target == "hub"


def test_unknown_target_raises_refs_error(fixture_repo: FixtureRepo) -> None:
    repo = fixture_repo("soft-orphans")
    with pytest.raises(RefsError, match="unknown doc target") as excinfo:
        build_doc_refs_report(repo, _graph(repo), "no-such-doc")
    assert excinfo.value.code == 1


def test_target_outside_repo_raises_refs_error(fixture_repo: FixtureRepo) -> None:
    repo = fixture_repo("soft-orphans")
    with pytest.raises(RefsError, match="outside the repo") as excinfo:
        build_doc_refs_report(repo, _graph(repo), "../elsewhere.md")
    assert excinfo.value.code == 2


def test_symbol_owners_match_describe_patterns_via_fnmatch(fixture_repo: FixtureRepo) -> None:
    repo = fixture_repo("specificity")
    report = build_symbol_refs_report(_graph(repo), "app/planner/routing/router.py", repo)

    # Both the broad `app/planner/**` claim (planner) and the narrower
    # `app/planner/routing/*.py` claim (routing) own the symbol; owners are
    # sorted by doc path.
    assert [(hit.doc_id, hit.match) for hit in report.owners] == [
        ("planner", "app/planner/**"),
        ("routing", "app/planner/routing/*.py"),
    ]
    assert report.references == []


def test_symbol_references_come_from_claim_evidence(fixture_repo: FixtureRepo) -> None:
    repo = fixture_repo("soft-lifecycle")
    report = build_symbol_refs_report(_graph(repo), "0001-good.md", repo)

    assert report.owners == []
    assert [(hit.doc_id, hit.match) for hit in report.references] == [
        ("stale-claim", "docs/80-evolution/rfcs/0001-good.md"),
    ]


def test_blank_symbol_query_is_rejected(fixture_repo: FixtureRepo) -> None:
    repo = fixture_repo("specificity")
    with pytest.raises(RefsError, match="cannot be empty") as excinfo:
        build_symbol_refs_report(_graph(repo), "   ", repo)
    assert excinfo.value.code == 2


def test_doc_refs_json_shape(fixture_repo: FixtureRepo) -> None:
    repo = fixture_repo("soft-orphans")
    report = build_doc_refs_report(repo, _graph(repo), "hub")

    data = json.loads(doc_refs_report_to_json(report))
    assert set(data) == {"target", "strong", "weak"}
    assert data["target"] == "hub"
    assert all(set(hit) == {"doc_id", "path", "line"} for hit in data["weak"])


def test_symbol_refs_json_shape(fixture_repo: FixtureRepo) -> None:
    repo = fixture_repo("specificity")
    report = build_symbol_refs_report(_graph(repo), "app/planner/routing/router.py", repo)

    data = json.loads(symbol_refs_report_to_json(report))
    assert set(data) == {"symbol", "owners", "references"}
    assert all(set(hit) == {"doc_id", "path", "line", "match"} for hit in data["owners"])
