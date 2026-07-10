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
    build_context_report,
    context_report_should_fail,
    context_report_to_json,
)

FixtureRepo = Callable[[str], Path]


def _config(repo: Path) -> IrminsulConfig:
    return load(find_config(repo))


def test_path_mode_source_file_resolves_owning_doc(fixture_repo: FixtureRepo) -> None:
    repo = fixture_repo("good")
    report = build_context_report(repo, _config(repo), target_path=repo / "app" / "composer.py")

    assert report.mode == "path"
    assert report.unmatched == []
    assert len(report.results) == 1
    result = report.results[0]
    assert result.input == ["app/composer.py"]
    assert result.owner.id == "composer"
    assert result.owner.path == "docs/20-components/composer.md"
    assert result.source_claims == ["app/composer.py"]
    assert result.entrypoint == "app/composer.py"
    assert result.tests == ["tests/test_composer.py"]
    assert result.doc_co_changed is True
    assert not context_report_should_fail(report)


def test_path_mode_doc_file_resolves_to_its_own_node(fixture_repo: FixtureRepo) -> None:
    repo = fixture_repo("good")
    target = repo / "docs" / "20-components" / "composer.md"
    report = build_context_report(repo, _config(repo), target_path=target)

    assert [result.owner.id for result in report.results] == ["composer"]
    assert report.results[0].input == ["docs/20-components/composer.md"]


def test_path_mode_prefers_most_specific_claim(fixture_repo: FixtureRepo) -> None:
    repo = fixture_repo("specificity")
    config = _config(repo)

    routed = build_context_report(
        repo, config, target_path=repo / "app" / "planner" / "routing" / "router.py"
    )
    assert [result.owner.id for result in routed.results] == ["routing"]
    assert routed.results[0].source_claims == ["app/planner/routing/*.py"]

    handled = build_context_report(
        repo, config, target_path=repo / "app" / "planner" / "handler.py"
    )
    assert [result.owner.id for result in handled.results] == ["planner"]
    assert handled.results[0].source_claims == ["app/planner/**"]


def test_path_mode_unclaimed_file_is_unmatched_and_fails(fixture_repo: FixtureRepo) -> None:
    repo = fixture_repo("good")
    report = build_context_report(repo, _config(repo), target_path=repo / "irminsul.toml")

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


def test_exactly_one_input_mode_is_required(fixture_repo: FixtureRepo) -> None:
    repo = fixture_repo("good")
    config = _config(repo)

    with pytest.raises(ContextError, match="exactly one input mode") as excinfo:
        build_context_report(repo, config)
    assert excinfo.value.code == 2

    with pytest.raises(ContextError, match="exactly one input mode"):
        build_context_report(repo, config, target_path=repo / "app", topic="composer")


def test_blank_topic_and_missing_path_are_rejected(fixture_repo: FixtureRepo) -> None:
    repo = fixture_repo("good")
    config = _config(repo)

    with pytest.raises(ContextError, match="cannot be empty") as excinfo:
        build_context_report(repo, config, topic="   ")
    assert excinfo.value.code == 2

    with pytest.raises(ContextError, match="does not exist") as excinfo:
        build_context_report(repo, config, target_path=repo / "app" / "nope.py")
    assert excinfo.value.code == 1


def test_json_report_shape_is_stable(fixture_repo: FixtureRepo) -> None:
    repo = fixture_repo("good")
    report = build_context_report(repo, _config(repo), target_path=repo / "app" / "composer.py")

    data = json.loads(context_report_to_json(report))
    assert data["version"] == 1
    assert data["mode"] == "path"
    assert set(data) == {"version", "mode", "results", "unmatched"}
    assert set(data["results"][0]) == {
        "input",
        "owner",
        "source_claims",
        "entrypoint",
        "tests",
        "depends_on",
        "depends_on_missing",
        "depended_on_by",
        "findings",
        "hints",
        "doc_co_changed",
    }
    assert set(data["results"][0]["owner"]) == {
        "id",
        "title",
        "path",
        "status",
        "audience",
        "tier",
    }
