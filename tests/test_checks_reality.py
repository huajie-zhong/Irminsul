"""Tests for RealityCheck."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from irminsul.checks.reality import RealityCheck
from irminsul.config import load
from irminsul.docgraph import build_graph


def _run(repo: Path) -> list:
    cfg = load(repo / "irminsul.toml")
    graph = build_graph(repo, cfg)
    return RealityCheck().run(graph)


def test_good_fixture_has_no_reality_findings(
    fixture_repo: Callable[[str], Path],
) -> None:
    findings = _run(fixture_repo("good"))
    assert findings == []


def test_speculative_keywords_flagged(
    fixture_repo: Callable[[str], Path],
) -> None:
    findings = _run(fixture_repo("soft-reality"))
    assert len(findings) >= 1
    messages = [f.message for f in findings]
    assert any(
        "planned" in m or "sprint" in m or "deferred" in m or "roadmap" in m for m in messages
    )


def test_findings_have_line_numbers(
    fixture_repo: Callable[[str], Path],
) -> None:
    findings = _run(fixture_repo("soft-reality"))
    assert all(f.line is not None and f.line > 0 for f in findings)


def test_only_layers_that_forbid_speculation_are_checked(
    fixture_repo: Callable[[str], Path],
) -> None:
    findings = _run(fixture_repo("soft-reality"))
    assert all(f.path is not None and "components" in f.path.as_posix() for f in findings)


def test_code_spans_and_fences_are_not_speculation(tmp_path: Path) -> None:
    (tmp_path / "irminsul.toml").write_text(
        'project_name = "r"\n[paths]\ndocs_root = "docs"\nsource_roots = []\n', encoding="utf-8"
    )
    doc = tmp_path / "docs" / "components" / "claims.md"
    doc.parent.mkdir(parents=True)
    doc.write_text(
        "---\nid: claims\ntitle: Claims\nstatus: stable\n---\n\n"
        "# Claims\n\nA claim state is `planned` or `enabled`.\n\n"
        "```yaml\nstate: planned\n```\n\nThe roadmap moves on.\n",
        encoding="utf-8",
    )
    findings = _run(tmp_path)
    lines = doc.read_text(encoding="utf-8").splitlines()
    assert [lines[f.line - 1] for f in findings] == ["The roadmap moves on."]


def _doc(root: Path, rel: str, body: str) -> Path:
    if not (root / "irminsul.toml").exists():
        (root / "irminsul.toml").write_text(
            'project_name = "r"\n[paths]\ndocs_root = "docs"\nsource_roots = []\n',
            encoding="utf-8",
        )
    doc = root / "docs" / rel
    doc.parent.mkdir(parents=True, exist_ok=True)
    slug = doc.stem
    doc.write_text(
        f"---\nid: {slug}\ntitle: T\nstatus: stable\n---\n\n# T\n\n{body}",
        encoding="utf-8",
    )
    return doc


def test_history_narration_is_flagged_in_layers_that_describe_the_present(
    tmp_path: Path,
) -> None:
    _doc(tmp_path, "components/store.md", "The store previously used SQLite.\n")
    _doc(tmp_path, "guides/migrate.md", "The store previously used SQLite.\n")
    findings = _run(tmp_path)
    assert [(f.code, f.path.as_posix()) for f in findings] == [
        ("reality/history-narration", "docs/components/store.md")
    ]


def test_decision_wording_needs_a_decision_link_in_its_paragraph(tmp_path: Path) -> None:
    _doc(
        tmp_path,
        "guides/storage.md",
        "We chose SQLite for storage.\n\n"
        "We chose Postgres for search, see\n[the record](../decisions/0001-search.md).\n\n"
        "We decided on Redis, see [the record](../decisions/redis.md).\n",
    )
    findings = _run(tmp_path)
    assert [f.code for f in findings] == ["reality/unrecorded-decision"]
    assert "chose" in findings[0].message


def test_decision_records_themselves_are_not_flagged(tmp_path: Path) -> None:
    _doc(tmp_path, "decisions/0001-search.md", "We chose Postgres.\n")
    assert _run(tmp_path) == []


def test_a_link_into_a_renamed_decisions_folder_records_the_decision(tmp_path: Path) -> None:
    from irminsul.checks.reality import RealityCheck
    from irminsul.config import load
    from irminsul.docgraph import build_graph

    (tmp_path / "irminsul.toml").write_text(
        'project_name = "r"\n[paths]\ndocs_root = "docs"\nsource_roots = []\n'
        '[layers.decisions]\npath = "adr"\n',
        encoding="utf-8",
    )
    doc = tmp_path / "docs" / "architecture" / "a.md"
    doc.parent.mkdir(parents=True)
    doc.write_text(
        "---\nid: a\ntitle: A\nstatus: stable\n---\n\n# A\n\n"
        "We chose SQLite, see [the record](../adr/sqlite.md).\n",
        encoding="utf-8",
    )
    findings = RealityCheck().run(build_graph(tmp_path, load(tmp_path / "irminsul.toml")))
    assert [f.code for f in findings if f.code == "reality/unrecorded-decision"] == []


def test_a_nested_rfcs_layer_is_not_a_decisions_layer(tmp_path: Path) -> None:
    from irminsul.config import load
    from irminsul.docgraph import build_graph, is_decision, is_rfc

    (tmp_path / "irminsul.toml").write_text(
        'project_name = "r"\n[paths]\ndocs_root = "docs"\nsource_roots = []\n'
        '[layers.rfcs]\npath = "decisions/rfcs"\n',
        encoding="utf-8",
    )
    doc = tmp_path / "docs" / "decisions" / "rfcs" / "plan.md"
    doc.parent.mkdir(parents=True)
    doc.write_text("---\nid: plan\ntitle: P\nstatus: draft\n---\n\n# P\n", encoding="utf-8")
    config = load(tmp_path / "irminsul.toml")
    node = build_graph(tmp_path, config).nodes["plan"]
    assert is_rfc(node, config) and not is_decision(node, config)
