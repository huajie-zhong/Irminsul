"""Tests for GlossaryDisciplineCheck."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from irminsul.checks.base import Severity
from irminsul.checks.glossary import (
    GlossaryDisciplineCheck,
    _blank_preserve_newlines,
    _parse_glossary_entries,
    _parse_glossary_terms,
)
from irminsul.config import find_config, load
from irminsul.docgraph import build_graph


def test_redefined_term_warned(fixture_repo: Callable[[str], Path]) -> None:
    repo = fixture_repo("soft-glossary")
    config = load(find_config(repo))
    graph = build_graph(repo, config)
    findings = GlossaryDisciplineCheck().run(graph)
    flagged_ids = {
        f.doc_id for f in findings if f.severity == Severity.warning and "redefined" in f.message
    }
    assert "composer" in flagged_ids


def test_benign_mention_not_redefined(fixture_repo: Callable[[str], Path]) -> None:
    repo = fixture_repo("soft-glossary")
    config = load(find_config(repo))
    graph = build_graph(repo, config)
    findings = GlossaryDisciplineCheck().run(graph)
    flagged_ids = {
        f.doc_id for f in findings if f.severity == Severity.warning and "redefined" in f.message
    }
    assert "benign" not in flagged_ids


def test_missing_glossary_returns_empty(tmp_path: Path) -> None:
    """No GLOSSARY.md -> silent skip (project hasn't bootstrapped one)."""
    repo = tmp_path / "r"
    repo.mkdir()
    (repo / "irminsul.toml").write_text(
        'project_name = "r"\n'
        '[paths]\ndocs_root = "docs"\nsource_roots = []\n'
        '[checks]\nsoft_deterministic = ["glossary-discipline"]\n',
        encoding="utf-8",
    )
    (repo / "docs").mkdir()

    config = load(find_config(repo))
    graph = build_graph(repo, config)
    assert GlossaryDisciplineCheck().run(graph) == []


def test_parse_glossary_metadata_and_anti_terms() -> None:
    text = (
        "# Glossary\n\n"
        "## Composer\n\n"
        'match: ["Composer", "composer"]\n'
        'forbidden_synonyms: ["request composer"]\n'
        "case_sensitive: false\n\n"
        "The composer.\n\n"
        "## Planner\n\nThe planner.\n\n"
        "## Anti-Glossary\n\n"
        "- thing\n"
        "- stuff\n"
    )
    entries, anti, issues = _parse_glossary_entries(text)
    composer = entries[0]
    planner = entries[1]
    assert issues == []
    assert composer.term == "Composer"
    assert composer.match_terms == ("Composer", "composer")
    assert composer.forbidden_synonyms == ("request composer",)
    assert composer.case_sensitive is False
    assert composer.has_metadata is True
    assert planner.has_metadata is False
    assert "thing" in anti
    assert "stuff" in anti


def test_parse_glossary_terms_separates_anti_terms() -> None:
    text = (
        "# Glossary\n\n"
        "## Composer\n\nThe composer.\n\n"
        "## Planner\n\nThe planner.\n\n"
        "## Anti-Glossary\n\n"
        "- thing\n"
        "- stuff\n"
    )
    terms, anti = _parse_glossary_terms(text)
    assert terms == {"Composer", "Planner"}
    assert "thing" in anti
    assert "stuff" in anti


def test_invalid_metadata_reports_warning(tmp_path: Path) -> None:
    repo = _write_repo(
        tmp_path,
        glossary=(
            "# Glossary\n\n## DocGraph\n\nmatch: DocGraph\ncase_sensitive: maybe\n\nDefinition.\n"
        ),
        docs={"docs/20-components/docgraph.md": "Mentions DocGraph."},
    )
    findings = _run_glossary(repo)
    messages = [finding.message for finding in findings]
    assert any("`match` must be an inline string list" in message for message in messages)
    assert "`case_sensitive` must be true or false" in messages


def test_forbidden_synonym_warns(tmp_path: Path) -> None:
    repo = _write_repo(
        tmp_path,
        glossary=(
            "# Glossary\n\n"
            "## DocGraph\n\n"
            'match: ["DocGraph"]\n'
            'forbidden_synonyms: ["doc system"]\n'
            "case_sensitive: true\n\n"
            "Definition.\n"
        ),
        docs={"docs/20-components/widget.md": "The doc system builds a graph."},
    )
    findings = _run_glossary(repo)
    assert any(
        finding.severity == Severity.warning and "forbidden synonym 'doc system'" in finding.message
        for finding in findings
    )


def test_unlinked_term_use_is_info(tmp_path: Path) -> None:
    repo = _write_repo(
        tmp_path,
        glossary=(
            "# Glossary\n\n"
            "## DocGraph\n\n"
            'match: ["DocGraph"]\n'
            "case_sensitive: true\n\n"
            "Definition.\n"
        ),
        docs={"docs/20-components/widget.md": "The DocGraph is built once."},
    )
    findings = _run_glossary(repo)
    assert any(
        finding.severity == Severity.info
        and "used without linking" in finding.message
        and finding.doc_id == "widget"
        for finding in findings
    )


def test_existing_glossary_link_suppresses_info(tmp_path: Path) -> None:
    repo = _write_repo(
        tmp_path,
        glossary=(
            "# Glossary\n\n"
            "## DocGraph\n\n"
            'match: ["DocGraph"]\n'
            "case_sensitive: true\n\n"
            "Definition.\n"
        ),
        docs={
            "docs/20-components/widget.md": (
                "The [DocGraph](../GLOSSARY.md#docgraph) is built once."
            )
        },
    )
    findings = _run_glossary(repo)
    assert not any(finding.severity == Severity.info for finding in findings)


def test_local_glossary_anchor_suppresses_info_for_glossary_doc(tmp_path: Path) -> None:
    repo = _write_repo(
        tmp_path,
        glossary=(
            "# Glossary\n\n"
            "## DocGraph\n\n"
            'match: ["DocGraph"]\n'
            "case_sensitive: true\n\n"
            "The [DocGraph](#docgraph) is canonical.\n"
        ),
        docs={},
        glossary_path="docs/20-components/GLOSSARY.md",
        glossary_frontmatter=True,
    )

    findings = _run_glossary(repo)
    assert not any(
        finding.severity == Severity.info and finding.doc_id == "glossary" for finding in findings
    )


def test_unused_declared_term_warns(tmp_path: Path) -> None:
    repo = _write_repo(
        tmp_path,
        glossary=(
            "# Glossary\n\n"
            "## DocGraph\n\n"
            'match: ["DocGraph"]\n'
            "case_sensitive: true\n\n"
            "Definition.\n"
        ),
        docs={"docs/20-components/widget.md": "No matching term here."},
    )
    findings = _run_glossary(repo)
    assert any(
        finding.severity == Severity.warning and "declared but unused" in finding.message
        for finding in findings
    )


def test_plural_forms_must_be_explicit(tmp_path: Path) -> None:
    repo = _write_repo(
        tmp_path,
        glossary=(
            "# Glossary\n\n"
            "## Doc atom\n\n"
            'match: ["Doc atom"]\n'
            "case_sensitive: true\n\n"
            "Definition.\n"
        ),
        docs={"docs/20-components/widget.md": "Doc atoms are separate files."},
    )
    findings = _run_glossary(repo)
    assert any("declared but unused" in finding.message for finding in findings)
    assert not any(finding.severity == Severity.info for finding in findings)


def test_blank_preserve_newlines_keeps_shape() -> None:
    assert _blank_preserve_newlines("abc\n`x`") == "   \n   "


def _run_glossary(repo: Path) -> list:
    config = load(find_config(repo))
    graph = build_graph(repo, config)
    return GlossaryDisciplineCheck().run(graph)


def _write_repo(
    tmp_path: Path,
    *,
    glossary: str,
    docs: dict[str, str],
    glossary_path: str = "docs/GLOSSARY.md",
    glossary_frontmatter: bool = False,
) -> Path:
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "irminsul.toml").write_text(
        'project_name = "repo"\n'
        '[paths]\ndocs_root = "docs"\nsource_roots = []\n'
        '[checks]\nsoft_deterministic = ["glossary-discipline"]\n'
        f'[checks.glossary_discipline]\nglossary_path = "{glossary_path}"\n',
        encoding="utf-8",
    )
    (repo / "docs").mkdir()
    glossary_body = glossary
    if glossary_frontmatter:
        glossary_body = (
            "---\n"
            "id: glossary\n"
            "title: Glossary\n"
            "audience: reference\n"
            "tier: 1\n"
            "status: stable\n"
            "---\n\n"
            f"{glossary}"
        )
    glossary_file = repo / glossary_path
    glossary_file.parent.mkdir(parents=True, exist_ok=True)
    glossary_file.write_text(glossary_body, encoding="utf-8")
    for rel_path, body in docs.items():
        path = repo / rel_path
        path.parent.mkdir(parents=True, exist_ok=True)
        doc_id = path.stem
        path.write_text(
            "---\n"
            f"id: {doc_id}\n"
            f"title: {doc_id}\n"
            "audience: explanation\n"
            "tier: 3\n"
            "status: stable\n"
            "---\n\n"
            f"# {doc_id}\n\n"
            f"{body}\n",
            encoding="utf-8",
        )
    return repo
