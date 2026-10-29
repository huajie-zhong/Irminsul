"""Unit tests for `irminsul.context.build_context_report` and its JSON shape.

These call the report builder directly against fixture repos (no CLI),
pinning ownership resolution, mode selection, and the serialized contract
agents consume.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from pathlib import Path

import pytest

from irminsul.config import IrminsulConfig, find_config, load
from irminsul.context import (
    ContextError,
    _bound_excerpt,
    _first_substantive_block,
    build_context_report,
    context_report_should_fail,
    context_report_to_json,
)

from .conftest import load_graph, write_config, write_doc

FixtureRepo = Callable[[str], Path]


def _config(repo: Path) -> IrminsulConfig:
    return load(find_config(repo))


def test_path_mode_source_file_resolves_owning_doc(fixture_repo: FixtureRepo) -> None:
    repo = fixture_repo("good")
    report = build_context_report(repo, _config(repo), target_paths=[repo / "app" / "composer.py"])

    assert report.mode == "path"
    assert report.unmatched == []
    assert len(report.results) == 1
    result = report.results[0]
    assert result.input == ["app/composer.py"]
    assert result.owner.id == "composer"
    assert result.owner.path == "docs/components/composer.md"
    assert result.source_claims == ["app/composer.py"]
    assert result.entrypoint == "app/composer.py"
    assert result.tests == ["tests/test_composer.py"]
    assert not context_report_should_fail(report)


def test_path_mode_doc_file_resolves_to_its_own_node(fixture_repo: FixtureRepo) -> None:
    repo = fixture_repo("good")
    target = repo / "docs" / "components" / "composer.md"
    report = build_context_report(repo, _config(repo), target_paths=[target])

    assert [result.owner.id for result in report.results] == ["composer"]
    assert report.results[0].input == ["docs/components/composer.md"]


def test_path_mode_aggregates_one_owner(fixture_repo: FixtureRepo) -> None:
    repo = fixture_repo("good")
    target = repo / "app" / "composer.py"

    report = build_context_report(repo, _config(repo), target_paths=[target, target])

    assert report.mode == "path"
    assert [result.owner.id for result in report.results] == ["composer"]
    assert report.results[0].input == ["app/composer.py"]
    assert report.validation is None
    assert report.next_actions[-1].command == "irminsul context --after-edit"


def test_path_mode_prefers_most_specific_claim(fixture_repo: FixtureRepo) -> None:
    repo = fixture_repo("specificity")
    config = _config(repo)

    routed = build_context_report(
        repo, config, target_paths=[repo / "app" / "planner" / "routing" / "router.py"]
    )
    assert [result.owner.id for result in routed.results] == ["routing"]
    assert routed.results[0].source_claims == ["app/planner/routing/*.py"]

    handled = build_context_report(
        repo, config, target_paths=[repo / "app" / "planner" / "handler.py"]
    )
    assert [result.owner.id for result in handled.results] == ["planner"]
    assert handled.results[0].source_claims == ["app/planner/**"]


def test_path_mode_unclaimed_file_is_unmatched_and_fails(fixture_repo: FixtureRepo) -> None:
    repo = fixture_repo("good")
    report = build_context_report(repo, _config(repo), target_paths=[repo / "irminsul.toml"])

    assert report.results == []
    assert [item.path for item in report.unmatched] == ["irminsul.toml"]
    assert report.unmatched[0].reason == "no owning doc found"
    assert context_report_should_fail(report)


def test_topic_mode_matches_and_misses(fixture_repo: FixtureRepo) -> None:
    repo = fixture_repo("good")
    config = _config(repo)

    hit = build_context_report(repo, config, topic="composer")
    assert hit.mode == "topic"
    assert [result.owner.id for result in hit.results] == ["composer"]
    assert hit.results[0].input == ["composer"]

    miss = build_context_report(repo, config, topic="no-such-topic")
    assert miss.results == []
    # An empty topic result is not a failure (unlike path mode).
    assert not context_report_should_fail(miss)


def test_topic_mode_multi_word_query_matches_terms_across_fields(fixture_repo: FixtureRepo) -> None:
    repo = fixture_repo("good")
    config = _config(repo)

    # "composer" only appears in composer.md's id/title/path; "test" only
    # appears there via its `recommended_tests:` entry. Each term hits a different field.
    hit = build_context_report(repo, config, topic="composer test")
    assert [result.owner.id for result in hit.results] == ["composer"]

    miss = build_context_report(repo, config, topic="composer no-such-term")
    assert miss.results == []


def test_exactly_one_input_mode_is_required(fixture_repo: FixtureRepo) -> None:
    repo = fixture_repo("good")
    config = _config(repo)

    with pytest.raises(ContextError, match="exactly one input mode") as excinfo:
        build_context_report(repo, config)
    assert excinfo.value.code == 2

    with pytest.raises(ContextError, match="exactly one input mode"):
        build_context_report(repo, config, target_paths=[repo / "app"], topic="composer")


def test_blank_topic_and_missing_path_are_rejected(fixture_repo: FixtureRepo) -> None:
    repo = fixture_repo("good")
    config = _config(repo)

    with pytest.raises(ContextError, match="cannot be empty") as excinfo:
        build_context_report(repo, config, topic="   ")
    assert excinfo.value.code == 2

    with pytest.raises(ContextError, match="does not exist") as excinfo:
        build_context_report(repo, config, target_paths=[repo / "app" / "nope.py"])
    assert excinfo.value.code == 2


def test_json_report_shape_is_stable(fixture_repo: FixtureRepo) -> None:
    repo = fixture_repo("good")
    report = build_context_report(repo, _config(repo), target_paths=[repo / "app" / "composer.py"])

    data = json.loads(context_report_to_json(report))
    assert data["version"] == 1
    assert data["mode"] == "path"
    assert set(data) == {"version", "mode", "results", "unmatched", "claim_reviews", "next_actions"}
    assert set(data["results"][0]) == {
        "input",
        "owner",
        "source_claims",
        "entrypoint",
        "tests",
        "test_reasons",
        "depends_on",
        "depends_on_missing",
        "depended_on_by",
        "active_changes",
        "content",
    }
    assert set(data["results"][0]["owner"]) == {
        "id",
        "title",
        "path",
        "status",
    }


def test_content_excerpt_bounds_lines_and_characters() -> None:
    line_bounded, line_truncated = _bound_excerpt("\n".join(f"line {i}" for i in range(25)))
    char_bounded, char_truncated = _bound_excerpt("x" * 1_500)

    assert len(line_bounded.splitlines()) == 20
    assert line_truncated is True
    assert len(char_bounded) == 1_200
    assert char_bounded.endswith("...")
    assert char_truncated is True


def test_first_substantive_block_skips_multiline_html_comments() -> None:
    excerpt = _first_substantive_block("<!--\nmetadata\n-->\n# Heading\nVisible prose.\n")

    assert excerpt == ("Heading", "Visible prose.")


def test_a_hash_line_in_a_fence_does_not_end_the_boundary_excerpt(tmp_path: Path) -> None:
    from irminsul.context import _boundary_excerpt

    write_config(tmp_path)
    write_doc(
        tmp_path,
        "docs/components/core.md",
        doc_id="core",
        body=(
            "## Scope & Limitations\n\nDoes not own the shell.\n\n"
            "```sh\n# a comment, not a heading\n```\n\nNor the network.\n\n"
            "<!--\n# a heading in a comment\n-->\n\nNor the disk.\n\n## Next\n\nNot excerpted.\n"
        ),
    )

    excerpt = _boundary_excerpt(load_graph(tmp_path).nodes["core"])

    assert excerpt is not None
    assert "Nor the network." in excerpt.text and "Nor the disk." in excerpt.text
    assert "Not excerpted." not in excerpt.text


def test_a_claims_decisions_are_the_links_beside_its_marker(tmp_path: Path) -> None:
    from irminsul.context import _claim_decisions

    write_config(tmp_path)
    for slug in ("real", "reference", "quoted", "fenced", "elsewhere"):
        write_doc(tmp_path, f"docs/decisions/{slug}.md", doc_id=slug, body="Decided.")
    write_doc(
        tmp_path,
        "docs/components/core.md",
        doc_id="core",
        body=(
            "The rule holds, per [the record](../decisions/real.md) and [another][ref], not "
            "`[quoted](../decisions/quoted.md)`.\n"
            "```\n[fenced](../decisions/fenced.md)\n```\n"
            "claim:rule\n\n"
            "Apart from that, [a paragraph without the marker](../decisions/elsewhere.md).\n\n"
            "[ref]: ../decisions/reference.md\n"
        ),
    )
    graph = load_graph(tmp_path)

    found = _claim_decisions(graph, graph.nodes["core"], "rule")

    assert [ref.id for ref in found] == ["real", "reference"]
