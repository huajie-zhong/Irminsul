"""Tests for SupersessionCheck."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from irminsul.checks.supersession import SupersessionCheck
from irminsul.config import find_config, load
from irminsul.docgraph import build_graph


def _findings(repo: Path) -> list:
    config = load(find_config(repo))
    graph = build_graph(repo, config)
    return SupersessionCheck().run(graph)


def test_missing_deprecated_status_warned(fixture_repo: Callable[[str], Path]) -> None:
    repo = fixture_repo("soft-supersession")
    findings = _findings(repo)
    msgs = [f.message for f in findings]
    assert any("status is" in m for m in msgs)


def test_missing_superseded_by_warned(fixture_repo: Callable[[str], Path]) -> None:
    repo = fixture_repo("soft-supersession")
    findings = _findings(repo)
    msgs = [f.message for f in findings]
    assert any("superseded_by" in m for m in msgs)


def test_unknown_supersedes_id_errors() -> None:
    """Direct unit: build a tiny graph with a dangling supersedes pointer."""

    from irminsul.checks.base import Severity
    from irminsul.docgraph import DocGraph, DocNode
    from irminsul.frontmatter import AudienceEnum, DocFrontmatter, StatusEnum

    fm = DocFrontmatter(
        id="x",
        title="X",
        audience=AudienceEnum.explanation,
        tier=3,
        status=StatusEnum.stable,
        supersedes=["does-not-exist"],
    )
    node = DocNode(id="x", path=Path("x.md"), frontmatter=fm, body="")
    graph = DocGraph(nodes={"x": node}, by_path={Path("x.md"): node})

    findings = SupersessionCheck().run(graph)
    assert any(f.severity == Severity.error for f in findings)
    assert any("does-not-exist" in f.message for f in findings)


def test_orphaned_superseded_by_errors() -> None:
    from irminsul.checks.base import Severity
    from irminsul.docgraph import DocGraph, DocNode
    from irminsul.frontmatter import AudienceEnum, DocFrontmatter, StatusEnum

    fm = DocFrontmatter(
        id="lonely",
        title="L",
        audience=AudienceEnum.explanation,
        tier=3,
        status=StatusEnum.deprecated,
        superseded_by="ghost",
    )
    node = DocNode(id="lonely", path=Path("l.md"), frontmatter=fm, body="")
    graph = DocGraph(nodes={"lonely": node}, by_path={Path("l.md"): node})

    findings = SupersessionCheck().run(graph)
    assert any(f.severity == Severity.error and "ghost" in f.message for f in findings)


def test_rfc_supersession_is_left_to_relation_graph(
    fixture_repo: Callable[[str], Path],
) -> None:
    repo = fixture_repo("rfc-relations")
    config = load(find_config(repo))
    graph = build_graph(repo, config)

    assert SupersessionCheck().run(graph) == []


def test_generic_supersession_does_not_rewrite_rfc_target(
    fixture_repo: Callable[[str], Path],
) -> None:
    repo = fixture_repo("rfc-relations")
    component = repo / "docs" / "20-components" / "component.md"
    component.write_text(
        component.read_text(encoding="utf-8").replace(
            "describes: []", "describes: []\nsupersedes: [0001-base]"
        ),
        encoding="utf-8",
    )
    config = load(find_config(repo))
    graph = build_graph(repo, config)

    assert SupersessionCheck().run(graph) == []
