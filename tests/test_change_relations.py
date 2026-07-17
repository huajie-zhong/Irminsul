"""Tests for lifecycle-aware RFC relationship graphs (RFC 0042)."""

from __future__ import annotations

import json
from collections.abc import Callable
from pathlib import Path

import pytest
from typer.testing import CliRunner

from irminsul.change.relations import (
    RelationFilter,
    RelationGraph,
    build_relation_graph,
    format_relation_graph_plain,
    relation_graph_to_json,
)
from irminsul.cli import app
from irminsul.config import load

runner = CliRunner()


@pytest.fixture
def repo(fixture_repo: Callable[[str], Path]) -> Path:
    return fixture_repo("rfc-relations")


def _report(
    repo: Path,
    *,
    focus: str | None = None,
    relation: RelationFilter = "all",
) -> RelationGraph:
    config = load(repo / "irminsul.toml")
    return build_relation_graph(repo, config, focus=focus, relation=relation)


def test_repository_graph_includes_legacy_and_isolated_rfcs(repo: Path) -> None:
    report = _report(repo)
    nodes = {node.id: node for node in report.nodes}

    assert "component" not in nodes
    assert nodes["0004-legacy"].state is None
    assert nodes["0011-isolated"].state == "accepted"
    assert nodes["0011-isolated"].status == "stable"


def test_dependency_statuses_preserve_unknown_edges(repo: Path) -> None:
    report = _report(repo, relation="dependency")
    statuses = {(edge.source, edge.target): edge.status for edge in report.edges}

    assert statuses["0002-mid", "0001-base"] == "satisfied"
    assert statuses["0003-leaf", "0002-mid"] == "pending"
    assert statuses["0004-legacy", "0003-leaf"] == "pending"
    assert statuses["0005-rejected", "0001-base"] == "void"
    assert statuses["0006-implemented-bad", "0002-mid"] == "pending"
    assert statuses["0006-implemented-bad", "missing-rfc"] == "invalid"
    assert ("0003-leaf", "component") not in statuses

    issues = {(issue.code, issue.source, issue.target) for issue in report.issues}
    assert ("unknown-target", "0006-implemented-bad", "missing-rfc") in issues
    assert (
        "implemented-before-dependency",
        "0006-implemented-bad",
        "0002-mid",
    ) in issues
    assert (
        "implemented-before-dependency",
        "0006-implemented-bad",
        "missing-rfc",
    ) in issues


def test_supersession_statuses_and_effective_successor_conflict(repo: Path) -> None:
    report = _report(repo, relation="supersession")
    statuses = {(edge.source, edge.target): edge.status for edge in report.edges}

    assert statuses["0002-mid", "0001-base"] == "planned"
    assert statuses["0004-legacy", "0002-mid"] == "unknown"
    assert statuses["0005-rejected", "0001-base"] == "void"
    assert statuses["0006-implemented-bad", "0001-base"] == "effective"
    assert statuses["0007-implemented-split", "0001-base"] == "effective"

    conflict = next(
        issue for issue in report.issues if issue.code == "multiple-effective-successors"
    )
    assert conflict.target == "0001-base"
    assert conflict.members == ("0006-implemented-bad", "0007-implemented-split")


def test_cycles_self_references_and_reverse_pointer_are_explicit(repo: Path) -> None:
    report = _report(repo)
    cycles = {(cycle.relation, cycle.members) for cycle in report.cycles}

    assert ("dependency", ("0008-cycle-a", "0009-cycle-b")) in cycles
    assert ("supersession", ("0008-cycle-a", "0009-cycle-b")) in cycles
    assert ("dependency", ("0010-self",)) in cycles
    assert ("supersession", ("0010-self",)) in cycles

    issue_codes = {issue.code for issue in report.issues}
    assert "dependency-cycle" in issue_codes
    assert "supersession-cycle" in issue_codes
    assert "self-reference" in issue_codes
    assert "reverse-supersession-declaration" in issue_codes


def test_focused_query_returns_selected_weak_component(repo: Path) -> None:
    report = _report(repo, focus="0003", relation="dependency")

    assert report.focus == "0003-leaf"
    assert {node.id for node in report.nodes} == {
        "0001-base",
        "0002-mid",
        "0003-leaf",
        "0004-legacy",
        "0005-rejected",
        "0006-implemented-bad",
    }
    assert all(edge.relation == "dependency" for edge in report.edges)
    assert all(issue.relation == "dependency" for issue in report.issues)


def test_focused_isolated_query_keeps_focus_node(repo: Path) -> None:
    report = _report(repo, focus="0011-isolated")

    assert [node.id for node in report.nodes] == ["0011-isolated"]
    assert report.edges == ()
    assert report.cycles == ()
    assert report.issues == ()


def test_json_contract_is_stable_and_preserves_null_state(repo: Path) -> None:
    report = _report(repo, focus="0004-legacy")
    first = relation_graph_to_json(report)
    second = relation_graph_to_json(_report(repo, focus="0004-legacy"))
    data = json.loads(first)

    assert first == second
    assert list(data) == [
        "version",
        "relation",
        "focus",
        "nodes",
        "edges",
        "cycles",
        "issues",
    ]
    assert data["version"] == 1
    legacy = next(node for node in data["nodes"] if node["id"] == "0004-legacy")
    assert legacy["state"] is None
    assert list(data["edges"][0]) == [
        "relation",
        "source",
        "target",
        "status",
        "path",
        "line",
    ]


def test_plain_contract_is_ascii_and_keeps_all_sections(repo: Path) -> None:
    output = format_relation_graph_plain(_report(repo, focus="0011-isolated"))

    output.encode("ascii")
    assert "nodes:" in output
    assert "dependencies:\n  (none)" in output
    assert "supersessions:\n  (none)" in output
    assert "cycles:\n  (none)" in output
    assert "issues:\n  (none)" in output


def test_cli_graph_json_accepts_numeric_focus_and_exits_zero_with_issues(repo: Path) -> None:
    result = runner.invoke(
        app,
        ["change", "graph", "0006", "--format", "json", "--path", str(repo)],
    )

    assert result.exit_code == 0, result.output
    data = json.loads(result.output)
    assert data["focus"] == "0006-implemented-bad"
    assert any(issue["code"] == "implemented-before-dependency" for issue in data["issues"])


def test_cli_graph_accepts_repo_relative_path(repo: Path) -> None:
    result = runner.invoke(
        app,
        [
            "change",
            "graph",
            "docs/80-evolution/rfcs/0011-isolated.md",
            "--path",
            str(repo),
        ],
    )

    assert result.exit_code == 0, result.output
    assert "focus: 0011-isolated" in result.output


def test_cli_graph_is_read_only(repo: Path) -> None:
    rfc = repo / "docs" / "80-evolution" / "rfcs" / "0010-self.md"
    before = rfc.read_bytes()

    result = runner.invoke(app, ["change", "graph", "0010", "--path", str(repo)])

    assert result.exit_code == 0, result.output
    assert rfc.read_bytes() == before


@pytest.mark.parametrize(
    ("args", "message"),
    [
        (["--format", "yaml"], "unknown --format"),
        (["missing"], "no RFC found"),
        (["component"], "not an RFC"),
    ],
)
def test_cli_graph_usage_errors(repo: Path, args: list[str], message: str) -> None:
    result = runner.invoke(app, ["change", "graph", *args, "--path", str(repo)])

    assert result.exit_code == 2
    assert message in result.output


def test_cli_graph_rejects_unknown_relation(repo: Path) -> None:
    result = runner.invoke(
        app,
        ["change", "graph", "--relation", "unknown", "--path", str(repo)],
    )

    assert result.exit_code == 2
    assert "Invalid value" in result.output
