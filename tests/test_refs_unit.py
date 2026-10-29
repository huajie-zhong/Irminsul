"""Unit tests for the report builders in `irminsul.refs`.

These exercise the pure report-building functions directly against fixture
repos (no CLI), pinning backlink resolution and the JSON shape downstream tooling
parses.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from pathlib import Path

import pytest

from irminsul.refs import (
    RefsError,
    build_doc_refs_report,
    doc_refs_report_to_json,
    format_doc_refs_plain,
)

from .conftest import load_graph, write, write_config, write_doc

FixtureRepo = Callable[[str], Path]


def test_strong_backlinks_come_from_depends_on(fixture_repo: FixtureRepo) -> None:
    repo = fixture_repo("soft-lifecycle")
    report = build_doc_refs_report(repo, load_graph(repo), "0007-depends-on-only")

    assert report.target == "0007-depends-on-only"
    # The RFC's own `resolved_by` points the other way, so only `depends_on` names it.
    assert [hit.doc_id for hit in report.strong] == ["depends-on-only"]
    depends_hit = report.strong[0]
    assert depends_hit.path == "docs/components/depends-on-only.md"
    # Line points at the `- 0007-depends-on-only` entry inside the
    # `depends_on:` frontmatter list, not at the top of the file.
    assert depends_hit.line == 8
    assert report.weak == []


def test_a_record_lists_the_rfcs_that_name_it_through_resolved_by(
    fixture_repo: FixtureRepo,
) -> None:
    repo = fixture_repo("soft-lifecycle")
    report = build_doc_refs_report(repo, load_graph(repo), "0001-good-adr")

    lines = {hit.doc_id: hit.line for hit in report.strong}
    assert lines["0001-good"] == 7
    assert lines["0008-accepted-no-backlink"] == 8
    assert "0005-implicit-adr" not in lines
    for hit in report.strong:
        text = (repo / hit.path).read_text(encoding="utf-8").splitlines()[hit.line - 1]
        assert text.startswith("resolved_by:"), hit


def _guidance_repo(tmp_path: Path) -> Path:
    write_config(tmp_path, extra='extra_docs = ["README.md"]\n')
    write_doc(tmp_path, "docs/hub.md", doc_id="hub", body="Back to the [readme](../README.md).")
    write(tmp_path, "docs/AGENTS.md", "Start at [the hub](hub.md) or the [readme](../README.md).\n")
    write(tmp_path, "README.md", "# Top\n\n[Self](README.md), [the hub](docs/hub.md).\n")
    return tmp_path


def test_a_link_in_a_guidance_file_is_a_weak_hit_without_a_doc_id(tmp_path: Path) -> None:
    repo = _guidance_repo(tmp_path)
    report = build_doc_refs_report(repo, load_graph(repo), "hub")

    assert [(hit.doc_id, hit.path, hit.line) for hit in report.weak] == [
        (None, "README.md", 3),
        (None, "docs/AGENTS.md", 1),
    ]
    data = json.loads(doc_refs_report_to_json(report))
    assert data["weak"][0] == {"doc_id": None, "path": "README.md", "line": 3}
    assert "  docs/AGENTS.md:1" in format_doc_refs_plain(report).splitlines()


def test_a_guidance_file_is_a_target_with_every_link_to_it_as_a_weak_hit(tmp_path: Path) -> None:
    repo = _guidance_repo(tmp_path)
    for target in ("README.md", "./README.md", str(repo / "README.md")):
        report = build_doc_refs_report(repo, load_graph(repo), target)

        assert report.target == "README.md"
        assert report.strong == []
        assert [(hit.doc_id, hit.path, hit.line) for hit in report.weak] == [
            (None, "docs/AGENTS.md", 1),
            ("hub", "docs/hub.md", 10),
        ]


def test_a_strong_hit_through_implements_points_at_its_entry(fixture_repo: FixtureRepo) -> None:
    """The line was looked up under `depends_on` only, so an `implements` hit read 1."""
    repo = fixture_repo("soft-lifecycle")
    report = build_doc_refs_report(repo, load_graph(repo), "0001-good")

    assert [(hit.doc_id, hit.line) for hit in report.strong] == [("0001-good-adr", 7)]


def test_weak_backlinks_resolve_relative_markdown_links(fixture_repo: FixtureRepo) -> None:
    repo = fixture_repo("soft-orphans")
    report = build_doc_refs_report(repo, load_graph(repo), "hub")

    assert report.strong == []
    assert [hit.doc_id for hit in report.weak] == ["overview"]
    hit = report.weak[0]
    assert hit.path == "docs/architecture/overview.md"
    # The link lives in the final paragraph of overview.md; the reported line
    # is file-absolute (frontmatter offset included), not body-relative.
    assert hit.line == 13


def test_target_resolves_by_repo_relative_path(fixture_repo: FixtureRepo) -> None:
    repo = fixture_repo("soft-orphans")
    report = build_doc_refs_report(repo, load_graph(repo), "docs/components/hub.md")
    assert report.target == "hub"


def test_unknown_target_raises_refs_error(fixture_repo: FixtureRepo) -> None:
    repo = fixture_repo("soft-orphans")
    with pytest.raises(RefsError, match="unknown doc target") as excinfo:
        build_doc_refs_report(repo, load_graph(repo), "no-such-doc")
    assert excinfo.value.code == 2


def test_target_outside_repo_raises_refs_error(fixture_repo: FixtureRepo) -> None:
    repo = fixture_repo("soft-orphans")
    with pytest.raises(RefsError, match="outside the repo") as excinfo:
        build_doc_refs_report(repo, load_graph(repo), "../elsewhere.md")
    assert excinfo.value.code == 2


def test_doc_refs_json_shape(fixture_repo: FixtureRepo) -> None:
    repo = fixture_repo("soft-orphans")
    report = build_doc_refs_report(repo, load_graph(repo), "hub")

    data = json.loads(doc_refs_report_to_json(report))
    assert set(data) == {"target", "strong", "weak"}
    assert data["target"] == "hub"
    assert all(set(hit) == {"doc_id", "path", "line"} for hit in data["weak"])


def test_a_weak_hit_is_at_the_line_of_its_link(tmp_path: Path) -> None:
    write_config(tmp_path)
    write_doc(tmp_path, "docs/hub.md", doc_id="hub", body="Hub.")
    write_doc(
        tmp_path,
        "docs/guide.md",
        doc_id="guide",
        body="A paragraph that wraps\nonto a second line and then\npoints at [the hub](hub.md).\n",
    )

    report = build_doc_refs_report(tmp_path, load_graph(tmp_path), "hub")

    assert [(hit.doc_id, hit.line) for hit in report.weak] == [("guide", 12)]


def test_a_link_in_an_anchor_tag_is_a_weak_hit(tmp_path: Path) -> None:
    write_config(tmp_path)
    write_doc(tmp_path, "docs/hub.md", doc_id="hub", body="Hub.")
    write_doc(tmp_path, "docs/guide.md", doc_id="guide", body='See <a href="hub.md">the hub</a>.')

    report = build_doc_refs_report(tmp_path, load_graph(tmp_path), "hub")

    assert [(hit.doc_id, hit.line) for hit in report.weak] == [("guide", 10)]
